# RepoAudit-Agent v3 演示与交付指南

## 打开工作台

- 本机实时验收入口：<http://127.0.0.1:8775/>
- 本机纯静态回放：<http://127.0.0.1:8781/>
- 仓库：`/Users/moon/Documents/ai agent/github-hot-monitor`

预览进程关闭后，按 [RUNBOOK.md](RUNBOOK.md) 启动。普通实时入口使用 `python3 ops/scripts/start_local.py --port 8775`；本次费用受控的验收入口使用 `.venv/bin/python eval/v3_preview.py --port 8775`。

## 五分钟演示

1. **需求与入口（30秒）**：从发现榜加入候选，或直接输入 GitHub 仓库。三种场景分别回答“怎么实现”“哪些位置值得安全复核”“接入环境需要改什么”。
2. **架构调查（90秒）**：选择“Pydantic AI / Agno · 模型接入架构与地址传递”回放，跳到结果。沿 `base_url` 定义、参数字典与客户端构造核对矩阵、组件关系和原文。问题没有提供行号，行范围由工具定位。
3. **安全线索（60秒）**：切换“Python MCP SDK · 进程与环境传递线索”。先看覆盖范围，再点进程和环境线索。区分规则命中、上下文复核与待补查；正常进程启动或环境读取本身不能证明漏洞。
4. **部署适配（60秒）**：选择“Pydantic AI · Python 环境和模型网关适配”，展示版本矩阵、带来源的配置示例、用户自填项和待运行步骤。复制文本不会执行或修改项目。
5. **工程闭环（60秒）**：切换报告轮次，打开固定提交原文，导出 Markdown 或 Replay JSON。静态入口保留同一套图、卡片和证据交互，演示无需模型密钥。

早期三份 v2 回放仍在列表中，可展示 Python 3.10 双仓选型差异，以及当时需要人工指定行号的补查流程。新旧录制分别保留。

## 自己发起实时核查

选择部署适配，添加 `pydantic/pydantic-ai`，输入：

> 请核查 pyproject.toml 中声明的 Python 版本是否允许 Python 3.11，给出原文；这里只判断版本声明。

完成后点原文，追问：

> 引用同一提交的版本声明，列出本机安装前还需要验证的事项。

架构研报给出关注的源码路径和符号即可，无需行号。安全审计可写明 `src/mcp/client` 等仓库内目录，减少无关扫描。实时任务固定运行当时的默认分支提交；复现录制中的确切资料应选择回放。

## 交付物

| 内容 | 入口 |
|---|---|
| 当前实现与实际交付状态 | [DELIVERY_STATUS.md](DELIVERY_STATUS.md) |
| 安装、API配置与恢复 | [RUNBOOK.md](RUNBOOK.md) |
| 数据流、模块与学习练习 | [CODE_GUIDE.md](CODE_GUIDE.md) |
| 简历项目经历 | [RESUME_PROJECT.md](RESUME_PROJECT.md) |
| 逐阶段独立复核 | [V3_VALIDATION.md](V3_VALIDATION.md) |
| 实测与原始运行记录 | [v3评测报告](../../eval/v3/eval_report.md) |
| 真实回放清单 | [examples/manifest.json](examples/manifest.json) |
| 回放格式与校验规则 | [REPLAY_BUNDLE_SCHEMA.md](REPLAY_BUNDLE_SCHEMA.md) |

准确提交和标签见 [RELEASE_BASELINE.md](RELEASE_BASELINE.md)。交付包 `RepoAudit-Agent-v3-交付包-2026-11-14.zip` 包含源码、静态站点、回放、文档和评测；本机密钥与运行数据库不随包分发。

解压后在包目录运行：

```bash
python3 -m http.server 8000 --bind 127.0.0.1 --directory site
```

打开 <http://127.0.0.1:8000/> 即可演示。`VERSION.json` 记录提交和标签，`MANIFEST.json` 记录逐文件 SHA-256。代码按任务要求保留本地提交，新版线上 Pages 需后续推送发布。
