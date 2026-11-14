#!/usr/bin/env python3
"""Render measured attempts without replacing initial failures or filling target metrics."""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.v3_budget import DEFAULT_PATH
from eval.run_eval import save


def tokens(item):
    records = item.get('request_records', [])
    return sum(c.get('usage', {}).get('input_tokens', 0) + c.get('usage', {}).get('output_tokens', 0) for c in records)


def measured(item):
    calls = item.get('request_records', [])
    return {'input_tokens': sum(c.get('usage', {}).get('input_tokens', 0) for c in calls),
            'output_tokens': sum(c.get('usage', {}).get('output_tokens', 0) for c in calls),
            'lead_input_peak': max((c.get('usage', {}).get('input_tokens', 0) for c in calls if c['role'] == 'lead'), default=0),
            'duration_seconds': item.get('duration_seconds'),
            'estimated_usd': sum(c.get('estimated_usd', 0) for c in calls)}


def main():
    base = ROOT / 'eval/v3'
    batches = []
    for folder in sorted((base / 'runs').glob('*')):
        items = [json.loads(p.read_text()) for p in sorted(folder.glob('*.json')) if p.name != 'manifest.json']
        batches.append((folder.name, items))
    ledger = json.loads(DEFAULT_PATH.read_text())
    lines = ['# RepoAudit-Agent v3 实测报告', '', '运行模型：gpt-6.1-sol / low。费用为统一账本的保守估算；所有首次结果、重复和恢复按独立记录保留。', '',
             '## 费用与调用', '', f"已记录 {len(ledger['calls'])} 次请求；已知费用估算 ${ledger['estimated_usd']:.6f}，未知调用预留 ${ledger['reserved_usd']:.6f}，批准总上限 $5。", '',
             '[费用计算与计划](BUDGET_PLAN.md) · [逐次账本](budget_ledger.json)', '', '## 在线批次', '',
             '| 批次 | 评分2 / 实际次数 | 执行错误 | 记录 |', '| --- | --- | --- | --- |']
    for name, items in batches:
        passed = sum(x.get('grading', {}).get('score') == 2 for x in items)
        errors = sum(bool(x.get('error')) for x in items)
        lines.append(f'| {name} | {passed}/{len(items)} | {errors} | [原始记录](runs/{name}/manifest.json) |')
    lines += ['', '评分2表示该用例的预设标签与关键原文合同同时满足。多文件工作流只评分所要求片段是否被引用，不能把该项分数解释为漏洞检出准确率。', '', '## 冻结回归与 C3 重复', '']
    regression_batches = [(n, xs) for n, xs in batches if n.startswith('regression-')]
    for name, items in regression_batches:
        unique = {}; repeats = []
        for x in sorted(items, key=lambda x: x['attempt']):
            if x['id'] in unique: repeats.append(x)
            else: unique[x['id']] = x
        lines += [f'批次 `{name}`：首轮 {sum(x["grading"]["score"] == 2 for x in unique.values())}/{len(unique)}；额外重复 {sum(x["grading"]["score"] == 2 for x in repeats)}/{len(repeats)}。', '',
                  '| 用例/次数 | 分数 | 判断 | 模型 / Lead | 总 Tokens | Lead 输入峰值 | 耗时秒 |', '| --- | --- | --- | --- | --- | --- | --- |']
        for x in sorted(items, key=lambda x: x['attempt']):
            m = x.get('metrics', {}); g = x['grading']
            lines.append(f"| {x['id']} / {x['attempt']} | {g['score']} | {', '.join(g.get('observed', [])) or x.get('execution_status', '无结果')} | {m.get('model_calls', 0)} / {m.get('lead_calls', 0)} | {tokens(x)} | {m.get('lead_input_peak', 0)} | {x['duration_seconds']} |")
        failures = [x for x in items if x['grading']['score'] != 2]
        for x in failures: lines += ['', f"- {x['id']}：{x.get('error') or x['grading']['reason']}。首次记录保留，后续修复/恢复另列。"]
    lines += ['', '## 路由成本对照', '', '仅配对同源码哈希、同资料、同模型且三种路径均达到评分2的任务。超限或失败单列，不纳入 Token 节省分母。', '',
              '| 代码版本 / 用例 | 完整流程 Tokens | 自动路由 Tokens | 全文单轮 Tokens | 自动相对完整节省 | 自动 / 全文 |', '| --- | --- | --- | --- | --- | --- |']
    comparisons = []
    all_auto = [x for _, xs in regression_batches for x in xs]
    for name, items in batches:
        if not name.startswith('comparison-'): continue
        for id in dict.fromkeys(x['id'] for x in items):
            full = next((x for x in items if x['id'] == id and x['route_requested'] == 'full'), None)
            baseline = next((x for x in items if x['id'] == id and x['route_requested'] == 'full_text'), None)
            auto = next((x for x in all_auto if x['id'] == id and full and x.get('code_version', {}).get('evidence_source_sha256') == full.get('code_version', {}).get('evidence_source_sha256') and x['model'] == full['model'] and x['effort'] == full['effort'] and x['input_fixture_sha256'] == full['input_fixture_sha256']), None)
            pair = {'case': id, 'batch': name, 'code_version': (full or {}).get('code_version'), 'eligible': bool(full and auto and baseline and all(x['grading']['score'] == 2 and not x.get('error') for x in (full, auto, baseline)))}
            label = ((full or {}).get('code_version', {}).get('commit', 'unknown')[:7] + ' / ' + id)
            if pair['eligible']:
                f, a, b = tokens(full), tokens(auto), tokens(baseline)
                pair.update(full_tokens=f, auto_tokens=a, full_text_tokens=b, saved_vs_full_percent=100 * (1-a/f) if f else None, ratio_vs_full_text=a/b if b else None,
                            measurements={name: measured(record) for name, record in [('full',full),('auto',auto),('full_text',baseline)]},
                            automatic_route=auto.get('reports', [{}])[-1].get('execution_route'))
                lines.append(f'| {label} | {f} | {a} | {b} | {100*(1-a/f):.2f}% | {a/b:.3f}× |')
            else:
                pair['reason'] = '缺少同版本配对或存在未达标/超限/失败'
                lines.append(f'| {label} | — | — | — | 不纳入 | {pair["reason"]} |')
            comparisons.append(pair)
    latest_batch = max((p['batch'] for p in comparisons), default=None)
    eligible = [p for p in comparisons if p['eligible'] and p['batch'] == latest_batch]
    if eligible:
        f = sum(x['full_tokens'] for x in eligible); a = sum(x['auto_tokens'] for x in eligible); b = sum(x['full_text_tokens'] for x in eligible)
        lines += ['', f'最新批次 `{latest_batch}` 有效配对 {len(eligible)} 项：自动路由总 Tokens 相对完整流程变化为 {(a/f-1)*100:+.2f}%；自动路由 / 全文单轮为 {a/b:.3f}×。该结果限于本次小样本，未混合历史版本。']
        lines += ['', '输入/输出、Lead 单次峰值、耗时与估算费用保存在 [配对明细](comparison_summary.json)。A2 的 Compose 端口问题按保守规则仍走完整流程；两次结果的差异不是快速路由收益。']
    lines += ['', '## 真实录制', '', '| 案例 | 状态 | 报告轮数 | 总输入 / 输出 | Lead峰值 | 回放 |', '| --- | --- | --- | --- | --- | --- |']
    for path in sorted((base / 'recordings').glob('*.json')):
        item = json.loads(path.read_text()); m = item.get('metrics', {}); export = item.get('export', {})
        lines.append(f"| {item['case']} | {item['status']} | {len(item.get('reports', []))} | {m.get('known_input_tokens', 0)} / {m.get('known_output_tokens', 0)} | {m.get('lead_input_peak', 0)} | {export.get('path', item.get('export_error', '未导出'))} |")
    lines += ['', '## 取证合同与范围', '', '[四个多文件工具合同](multifile_tool_results.json)区分真实选取文件快照与构造安全样本；[真实工具扫描](live_tools_validation.json)保留固定提交、覆盖范围及截断。原16项冻结合同见[结果](offline_results.json)。', '',
              '源码引用存在性、Hash与行范围校验验证来源完整性；结论是否支持需求按固定合同和人工原文复核分别记录。v2 的 2.71 倍保留在历史报告，不混入本版对照。', '']
    (base / 'eval_report.md').write_text('\n'.join(lines))
    save(base / 'budget_ledger.json', ledger)
    save(base / 'comparison_summary.json', {'pairs': comparisons})
    print(str(base / 'eval_report.md'))

if __name__ == '__main__': main()
