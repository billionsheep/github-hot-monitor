# GitHub Hot Monitor

开源项目工程约束核查 Agent：输入一个公开 GitHub 仓库和 Python、容器部署或模型服务要求，模型按需读取固定提交的目录与文本，输出带来源引用的核查表。保留原有 GitHub 热门项目榜单。

## Agent 演示

技术栈：Python 3.11、FastAPI、Pydantic、SQLite、OpenAI Responses API / Function Calling、原生 JavaScript。

- 固定 commit SHA，证据保留原始行号、文件与片段 SHA-256、来源链接；同版本文件复用本地缓存。
- 模型使用 `gpt-6.1-sol` / low，仅可调用目录和文本片段读取工具，按要求补查证据。
- 输出“证据支持 / 证据冲突 / 信息不足 / 需要运行验证”，自动校验引用属于本次读取；语义支持在演示验收时对照原文核对。
- 每任务最多 6 次模型请求、8 次工具调用，展示 token 用量、耗时和停止原因。

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp -n .env.example .env.local
chmod 600 .env.local
```

用文本编辑器在 `.env.local` 填写 `LLM_API_KEY`，保留示例中的其他设置，然后启动：

```bash
.venv/bin/python ops/scripts/build_pages.py --state-dir data --web-dir web --out-dir public
.venv/bin/python -m uvicorn evidence.app:app --host 127.0.0.1 --port 8770
```

访问 <http://127.0.0.1:8770>。密钥保留在服务端，`.env.local` 和运行缓存已排除 Git。GitHub Pages 提供静态榜单，Agent 通过上述本地服务演示。

[项目状态](docs/project/README.md) · [运行说明](docs/project/RUNBOOK.md) · [真实验证](docs/project/R2_REAL_VALIDATION.md) · [演示脚本](docs/project/R2_DEMO.md) · [简历项目经历](docs/project/RESUME_PROJECT.md)

## 热门项目榜单功能

- 抓取候选仓库并保存快照（`data/snapshots/`）。
- 基于历史快照计算 `stars/day` 速度。
- 输出 Markdown 报告和结构化 JSON（`data/reports/latest.*`）。
- 前端页面支持分类榜单、搜索、语言筛选、最低星数筛选、项目画像（Trend / Frontier / Builder）。
- GitHub Actions 定时执行并自动发布到 GitHub Pages。

## 静态榜单运行

1. 设置 token（建议）：

```bash
export GITHUB_TOKEN=你的token
```

2. 执行扫描：

```bash
python3 ops/scripts/github_hot_monitor.py scan
```

3. 构建静态页面：

```bash
python3 ops/scripts/build_pages.py --state-dir data --web-dir web --out-dir public
```

4. 本地预览：

```bash
python3 -m http.server --directory public 8000
```

访问 `http://localhost:8000`。

## GitHub Pages 自动部署

仓库已提供工作流：[`.github/workflows/pages.yml`](.github/workflows/pages.yml)

首次使用需要在仓库里手动启用一次 Pages：

1. `Settings -> Pages`
2. `Build and deployment -> Source` 选择 `GitHub Actions`

- 触发方式：
  - 手动触发 `workflow_dispatch`
  - 每 6 小时自动执行（`0 */6 * * *`）
  - 推送 `ops/scripts/`、`web/`、工作流文件后自动执行
- 工作流行为：
  - 执行监控脚本更新 `data/`
  - 自动提交最新快照与报告到 `main`
  - 构建 `public/` 并发布到 GitHub Pages

建议在仓库 Secrets 配置 `GH_API_TOKEN`（避免 API 限流）。

## 常用命令

只关注某些方向：

```bash
python3 ops/scripts/github_hot_monitor.py scan \
  --topics ai,agent,developer-tools,automation \
  --query-days 21 \
  --min-stars 80 \
  --top 15
```

指定状态目录：

```bash
python3 ops/scripts/github_hot_monitor.py scan --state-dir /tmp/gh-hot
```

## 排名解释

- `Fastest Star Growth`：相对上次快照的升星速度（stars/day）。
- `Most Interesting`：趋势速度 + 最近活跃度 + 关注度（watchers）。
- `Most Advanced`：技术关键词匹配 + star/fork 强度。
- `Most Productive`：最近 push 频率 + issue 压力（open issues 相对 forks）+ 规模。
- `Overall Rank`：综合加权分（interesting 45% / advanced 30% / productive 25%）。

## 注意事项

- 第一次运行只会有静态分数，第二次以后才会有真实速度趋势。
- 未设置 token 时更容易触发 `403 rate limit exceeded`。
- 这是启发式评分，不是绝对结论，建议根据你关注领域调整 `topics` 和阈值。
