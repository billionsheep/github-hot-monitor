---
name: repoaudit-arch-research
description: 追踪入口、状态、模型接口与多仓架构差异。调用本机RepoAudit引擎，解析证据报告并提供Web复核链接。
---

# 架构研报

触发：追踪入口、状态、模型接口与多仓架构差异。 共同输入Schema与输出约定见 [INDEX](../INDEX.md)，只读取当前工作流需要的规范。

1. 确定目标公开仓库（1～3个）及用户的问题。在RepoAudit引擎目录运行CLI；将IDE当前项目的绝对目录传入 `--project`，先用 `inspect` 读取Python/配置声明。缺失或冲突时保留探测缺口，不以本机解释器版本冒充用户约束。
2. 确认本机服务可用：按 [运行说明](../../docs/project/RUNBOOK.md) 启动。服务端保存模型密钥，CLI和输出中无需携带密钥。本地检测结果属于调用方约束，目标仓库的结论仍须引用其固定提交。
3. 执行当前工作流，解析stdout中的JSON。任务未结束时用 `result --session` 查询；不把重复run当成轮询。模型调用沿用原引擎预算，遇到失败或预算不足保留已有证据和缺口。
4. 摘要列出每项四态结论、证据ID和下一步。遇到FAIL/RISK/UNVERIFIED时，明确提供 `review_url` 并让用户在工作台打开原文。配置建议呈现为可复制文本，按用户后续指示执行。

```bash
.venv/bin/python -m evidence.cli inspect --project /absolute/local-project
.venv/bin/python -m evidence.cli run --workflow arch_research --repo pydantic/pydantic-ai --project /absolute/local-project --query '追踪模型客户端创建入口、base_url参数转交和状态持久化；每个结论引用固定版本源码。'
```

离线演示：

```bash
.venv/bin/python -m evidence.cli replay --replay v3-architecture-gateway.json --workbench-url http://127.0.0.1:8781/
```

解释结果时：Python AST关系与规则线索，不推断未读取实现。 多仓顺序执行，Python采用AST，JS/TS、Shell和文档为规则线索；扫描上限24目录/24文本文件/1MiB，超限范围从报告继续位置核对。
