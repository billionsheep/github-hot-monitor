# RepoAudit-Agent 演示与交付指南

## 当前可打开的入口

- 本机实时工作台：<http://127.0.0.1:8774/>
- 本机纯静态回放：<http://127.0.0.1:8780/>
- 项目目录：`/Users/moon/Documents/ai agent/github-hot-monitor`

这些是当前预览进程；关闭后按下方命令启动。源码已固化为本地提交与标签 `repoaudit-demo-2026-11-13`，线上 GitHub Pages 尚未更新为此版。交付包的 `VERSION.json` 记录对应提交。

## 三分钟演示

**第 1 分钟：说明问题与选型差异。** 打开静态入口，进入“尽调”，选择“Pydantic AI / Agno · Python 选型与升级追问”，点击“跳到结果”，在“报告轮次”选择第 1 轮。展示 Python 3.10 条件下 Pydantic AI 的 FAIL 和 Agno 的 PASS。

**第 2 分钟：说明证据如何可信。** 点击 Pydantic AI 的“查看原文”，展示 `pyproject.toml` 第 48 行、完整 commit、片段哈希和固定来源；打开 GitHub 对照同一行。说明工具只读文件，静态声明与实际安装分别判断。

**第 3 分钟：说明 Agent 工程能力。** 切换第 2 轮，展示用户追问升级 Python 3.11 后两仓 PASS；查看工具 CACHE_HIT 和公开轨迹。补充可以导出报告和自包含 JSON、关闭后端后仍可回放；历史会话和检查点用于恢复。

如需展示信息不足与补查，切换“Pydantic AI · 模型服务地址源码补查”：第一轮资料不足，第二轮收窄问题并指定原文位置后完成参数转交核查。该演示保留真实过程。

## 本机实时演示

首次安装与配置见 [RUNBOOK.md](RUNBOOK.md)。本机 `.env.local` 已有配置时直接启动：

```bash
cd '/Users/moon/Documents/ai agent/github-hot-monitor'
python3 ops/scripts/start_local.py --port 8774
```

在候选池输入 `pydantic/pydantic-ai` 和 `agno-agi/agno`，问题可复制：

> 我们的现有项目暂时只能使用 Python 3.10。请核查两个仓库当前包声明是否允许 Python 3.10，分别引用原文并比较。仅判断声明，不要求安装运行。

完成后追问：

> 如果升级到 Python 3.11，两个仓库是否都满足？沿用本次固定提交并引用 requires-python 原文。

实时任务会固定当时最新提交，后续仓库变化可能改变结果；需要复现本次确切版本时选录制回放。矩阵上方提供 Markdown 和 Replay JSON 下载。

## 交付内容

| 内容 | 位置 |
|---|---|
| 产品现状、架构、验收和实际问题 | `docs/project/DELIVERY_STATUS.md` |
| 运行与本机 API 配置 | `docs/project/RUNBOOK.md` |
| 数据流、模块与学习练习 | `docs/project/CODE_GUIDE.md` |
| 可用于简历的项目经历 | `docs/project/RESUME_PROJECT.md` |
| 三份真实回放、冻结版本与用量 | `web/replays/`、`docs/project/examples/manifest.json` |
| 可阅读的真实报告 | `docs/project/examples/*.md` |
| 冻结案例、评测脚本与实测结果 | `eval/` |
| 可部署的静态站点 | 构建后的 `public/` |

另提供“RepoAudit-Agent-交付包-2026-11-13.zip”。解压后在目录内运行 `python3 -m http.server 8000 --bind 127.0.0.1 --directory site`，打开 <http://127.0.0.1:8000/>。压缩包包含源码、静态页面、原始回放、项目文档和评测记录；本机凭证、运行数据库不在包中。

## 分享给面试官

优先发静态站点链接或上述压缩包，附一句说明：“这是开源 Agent 框架工程约束核查工具；演示展示 Python 环境选型、固定源码证据和同一会话追问。”仓库推送并完成 Pages 工作流后才能使用线上新版链接；当前本地入口不能供他人在公网访问。
