# GitHub Hot Monitor

监控 GitHub 上升星最快的项目，并通过静态网页展示「升星趋势 / 有趣度 / 先进性 / 生产力 / 综合排名」。

## 功能

- 抓取候选仓库并保存快照（`data/snapshots/`）。
- 基于历史快照计算 `stars/day` 速度。
- 输出 Markdown 报告和结构化 JSON（`data/reports/latest.*`）。
- 前端页面支持分类榜单、搜索、语言筛选、最低星数筛选、项目画像（Trend / Frontier / Builder）。
- GitHub Actions 定时执行并自动发布到 GitHub Pages。

## 本地运行

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
