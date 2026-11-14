# RepoAudit 冻结评测

## v3 当前入口

- `v3/eval_report.md`：本次实测汇总；`v3/runs/`、`v3/recordings/` 保留逐次结果，失败与重试分开。
- `v3_budget.py`：所有 v3 线上回归、真实录制和验收页面共用5美元账本，保留超时未知请求预留。
- `run_v3_eval.py --batch regression`：13个在线用例，加 C3 两次重复；`--batch comparison` 对 A1–A4 运行强制完整和全文单轮，与同源码哈希的自动路由结果配对。
- `run_v3_multifile.py`：MCP 架构及两个构造安全对照的模型取证；只衡量预定引用合同，不能作为漏洞准确率。
- `record_v3_demo.py`：固定公开提交录制三种工作流。每次尝试与导出原包分别保留，新增回放不覆盖旧三份 v2 原文件。
- `v3_tool_cases.py`：四组多文件的离线工具合同；`validate_v3_delivery.py` 对交付回放与本机冻结文件缓存核对，需本次缓存存在。
- `summarize_v3.py`：从已有记录生成报告，不调用模型。费用、Tokens、Lead峰值、耗时和失败均来自运行记录。

下方保留 v2 的评测方法与历史结果；v3 的实际分母以新报告为准。

`golden_cases.json` 定义 16 个用例，A4 / B4 / C3 / D3 / E2；`fixtures/repositories.json` 保存构造仓库的冻结文本和哈希。构造内容明确标为 synthetic，不指称真实开源项目存在缺陷。

- `python eval/run_eval.py`：不联网，检查冻结资料、真实工具返回、引用护栏和外部内容编码契约。此结果不计作模型判断准确率。
- `python eval/run_eval.py --online --baseline --max-usd 3`：13 个语义用例使用本机模型配置运行完整 harness，并与相同冻结资料的全文单轮基线比较；3 个伪造引用用例由确定性护栏检查。调用前写入 manifest，保留实际用量、失败和逐例结果。不会读取或执行构造仓库代码。
- `python eval/run_eval.py --report <结果 JSON>`：从已有记录生成报告，不重新调用模型。

在线评分采用冻结 Evidence-Only Rubric：0 分为状态错误/运行失败，1 分为状态符合但缺少指定关键证据，2 分为状态和关键证据均符合。它衡量本测试集的标签与证据契约，不将任意自由文本语义或提示词注入防御概括为 100% 正确。

运行数据和数据库在 `.evidence-data/`；公开的 `eval_report.md` 与脱敏逐例结果保留实际计数。账单估算使用标准处理档，输入统一按缓存写入的较高费率估算，不冒充账户账单。价格来源：[OpenAI GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol)，核对日期 2026-11-13。

## 本次结果与真实素材

最终首轮 11/13 符合标签与关键证据契约。A2 网络中断后使用原检查点恢复为 PASS（无新增模型调用、保留 1 次未知调用）；恢复单独记录于 `recovery_results.json`，不覆盖首轮失败。C3 正文说明资料不足但状态为 FAIL，保留为标签不符合案例。

`fixtures/real_candidates.json` 另存真实 Pydantic AI / Agno 的选取文件、完整提交、逐文件哈希与抓取时间，明确为部分资料；包含各自 LICENSE。它们不混入 16 个构造用例的分母。真实端到端运行、回放与用量见 `docs/project/examples/manifest.json`。

`history/` 保留初次基线提示词协议错误及校正记录。最终评测已采用校正后的预取全文协议，并在多仓任务范围修复后完整重跑；最终报告不挑选历史最好分数。
