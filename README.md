# GitHub Hot Monitor

监控 GitHub 上升星最快的项目，并给出「有趣 / 先进 / 高生产力」排行榜。

## 目标

- 追踪最近一段时间（默认 30 天内创建）的热门仓库。
- 保存每次抓取快照，基于历史快照计算升星速度（stars/day）。
- 生成可读报告，帮助快速发现值得跟进的项目。

## 快速开始

1. 设置可选令牌（建议，避免 API 限流）：

```bash
export GITHUB_TOKEN=你的token
```

2. 运行一次扫描：

```bash
python3 ops/scripts/github_hot_monitor.py scan
```

3. 查看报告：

- 最新报告：`data/reports/latest.md`
- 历史快照：`data/snapshots/`

## 常用命令

只看你关心的方向（比如 AI + DevTools）：

```bash
python3 ops/scripts/github_hot_monitor.py scan \
  --topics ai,agent,developer-tools,automation \
  --query-days 21 \
  --min-stars 80 \
  --top 15
```

指定状态目录（适合 CI）：

```bash
python3 ops/scripts/github_hot_monitor.py scan --state-dir /tmp/gh-hot
```

## 排名解释

- `Fastest Star Growth`：相对上次快照的升星速度（stars/day）。
- `Most Interesting`：趋势速度 + 最近活跃度 + 关注度（watchers）。
- `Most Advanced`：技术关键词匹配 + star/fork 强度。
- `Most Productive`：最近 push 频率 + issue 压力（open issues 相对 forks）+ 规模。
- `Overall Rank`：综合加权分（interesting 45% / advanced 30% / productive 25%）。

## 建议的自动化方式

每天跑 2-4 次效果最好（第一次运行不计算速度，从第二次开始才有趋势）。

示例 `crontab`：

```cron
0 */6 * * * cd /Users/moon/code/github-hot-monitor && /usr/bin/python3 ops/scripts/github_hot_monitor.py scan >> data/cron.log 2>&1
```

## 注意事项

- 未设置 `GITHUB_TOKEN` 时，GitHub API 配额较低，可能触发限流。
- 这是启发式评分，不是绝对客观结论。建议按你的领域调整 `topics` 和阈值。
