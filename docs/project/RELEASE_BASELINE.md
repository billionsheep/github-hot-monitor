# RepoAudit-Agent 演示版本基线

## v3：2026-11-14

交付标签：`repoaudit-v3-demo-2026-11-14`。保留下面的v2基线，新增三个工作流、AST完整语句与参数转交补查、有界架构/安全扫描、确定性快速路由、四态校准、Replay2.0和真实演示。

交付包：`RepoAudit-Agent-v3-交付包-2026-11-14.zip`。包内 `VERSION.json` 是准确提交与标签的依据，`MANIFEST.json` 保存逐文件Hash。生成脚本拒绝脏工作区、错位标签、运行数据与疑似密钥，并逐项核对压缩包内容。

```bash
git rev-parse repoaudit-v3-demo-2026-11-14^{commit}
.venv/bin/python ops/scripts/package_delivery.py --tag repoaudit-v3-demo-2026-11-14 --output '../RepoAudit-Agent-v3-交付包-2026-11-14.zip'
```

测试与页面结果见 [v3阶段验收](V3_VALIDATION.md)，最新实际效果见 [v3评测报告](../../eval/v3/eval_report.md)。全部变更本地固化，未自动推送或发布。

## v2：保留的历史基线

固化日期：2026-11-13。版本标签：`repoaudit-demo-2026-11-13`。

此标签对应用户验收后的本地提交，固化源码、三份真实回放、冻结评测、运行文档和简历项目经历。后续修改从此基线继续，已录制的案例和原始评测结果保留。

## 交付范围

- 发现与候选池、1～3 仓约束核查、Lead/Sub 独立上下文和六类只读取证工具。
- SQLite WAL 检查点、租约与工具回执、历史恢复、同版本追问。
- SSE、判断矩阵、原文溯源、报告轮次选择、Markdown/Replay 导出和静态回放。
- 实际验收与评测记录、源码学习入口和可用于简历的项目材料。

详细状态见 [DELIVERY_STATUS.md](DELIVERY_STATUS.md)，演示见 [DELIVERY_GUIDE.md](DELIVERY_GUIDE.md)。

## 验证依据

Python 94/94、前端 13/13；进程硬退出后验证租约等待、到期恢复及已提交调用不重复。16 个冻结契约通过；三份回放的内容、来源、引用及清单哈希一致。

真实模型首轮 11/13 的结果原样保留：一例网络中断通过检查点恢复，一例缺少授权资料却使用 FAIL 标签。小样本没有证明 Token 降本；完整结果见 [评测报告](../../eval/eval_report.md)。

## 实测环境

| 组件 | 版本 |
|---|---|
| Python | 3.11.15 |
| FastAPI | 0.115.14 |
| Pydantic | 2.14.3 |
| HTTPX | 0.28.1 |
| Uvicorn | 0.34.3 |
| PyYAML | 6.0.2 |

直接依赖固定在 `requirements.txt`；运行模型沿用本机配置 `gpt-6.1-sol / low`。

## 查阅和复现

```bash
git show --stat repoaudit-demo-2026-11-13
git rev-parse repoaudit-demo-2026-11-13^{commit}
.venv/bin/python -m unittest discover -s tests -q
node --test tests/test_*.js
.venv/bin/python tests/phase2_crash_smoke.py
.venv/bin/python eval/run_eval.py
```

交付压缩包中的 `VERSION.json` 记录准确提交及标签，`MANIFEST.json` 记录包内文件哈希。实时数据和密钥保留在 Git 忽略的本机文件中。此基线已在本地提交，尚未推送或发布新版 Pages。
