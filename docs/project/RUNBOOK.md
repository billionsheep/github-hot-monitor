# 本地运行与复现

## 环境

采集和静态构建使用标准库；R1 服务使用 Python 3.11 和 `requirements.txt`，前端测试使用 Node.js。网页是原生 HTML/CSS/JavaScript。

## 启动已有数据页面

```bash
cd '/Users/moon/Documents/ai agent/github-hot-monitor'
python3 ops/scripts/build_pages.py --state-dir data --web-dir web --out-dir public
python3 -m http.server 8765 --bind 127.0.0.1 --directory public
```

访问 <http://127.0.0.1:8765>。终端按 Ctrl+C 停止服务。端口被占用时先访问已有服务，或换一个端口。

`build_pages.py` 会删除并重建指定的输出目录，因此 `--out-dir` 应固定使用可再生的 `public`，不要指向源码或资料目录。`public/` 已在 .gitignore 内。

## 测试

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_frontend.js
```

## 单独验证实时采集

```bash
python3 ops/scripts/github_hot_monitor.py scan \
  --topics agent --query-days 30 --min-stars 50 \
  --per-query 5 --top 5 \
  --state-dir /private/tmp/github-hot-monitor-practice
```

未配置 Token 时使用匿名 GitHub API，可能遇到限流。需要认证时通过 `GITHUB_TOKEN` 环境变量提供，不写进代码、报告或提交。当前代码会额外执行一个不限制 topic 的兜底查询，所以结果不一定全是 Agent 项目。

首次扫描没有历史快照，升星速度为 0；间隔至少两小时且仓库出现在前后快照中，才会计算有效速度。后续练习沿用同一个 state-dir。

要用练习数据预览，构建时改为对应 state-dir，之后刷新网页即可。

## 自动更新与排障

本地 HTTP 服务只提供静态文件，不会每六小时自行采集；六小时调度来自远端 `.github/workflows/pages.yml`。

- 页面加载失败：检查 `public/data/latest.json` 是否存在及服务是否仍在运行。
- 修改采集结果或 web 源码后：重跑构建，再刷新浏览器。
- 结果缺失：查看扫描 stderr 中的 `[warn] query failed`；当前部分查询失败仍可能生成报告。
- 浏览器 favicon 404：仓库没有站点图标，不影响榜单。

## 启动 R1 同源页面

```bash
cd '/Users/moon/Documents/ai agent/github-hot-monitor'
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python ops/scripts/build_pages.py --state-dir data --web-dir web --out-dir public
# 如本机已用 gh 登录，可选择仅在当前终端提供凭证：
export GITHUB_TOKEN="$(gh auth token)"
.venv/bin/python -m uvicorn evidence.app:app --host 127.0.0.1 --port 8768
```

访问 <http://127.0.0.1:8768>，输入 `owner/repo` 或 `https://github.com/owner/repo`。默认读取 README，展开目录可选其他文件。也可匿名访问；遇到限流时等待额度恢复或提供服务端令牌。快照和缓存保存在 `.evidence-data/evidence.sqlite3`，已排除 Git。抓取时间是首次成功读取该版本对象的时间。修改网页后重新构建，修改服务代码后重启；Ctrl+C 停止服务。

目录提示截断时其他路径的存在状态未知。文件限制 512 KiB；片段限制 200 行、16 KiB。单行超长时界面显示截断提示及固定来源链接。

## R1.1 阅读与复现

页面加载时检测 `/api/capabilities`，静态页面禁用提交并提示启动本地服务。创建快照后使用根目录和面包屑浏览；常用文件入口只来自已读取的目录。选择文件后展开原文逐行查看，使用指定行跳转和上一段/下一段浏览实际访问历史；commit、完整文件 SHA-256、片段 SHA-256 与证据 ID 可复制。空文件显示无行号。单行超过上限时查看固定版本来源。

当前新版服务在 8768；8766 是本机已有的旧版进程。若 8768 已占用，使用其他空闲端口启动并访问该端口。用静态模式验证可另开终端运行 `.venv/bin/python -m http.server 8769 --bind 127.0.0.1 --directory public`。

接口契约可在本地 `http://127.0.0.1:8768/docs` 查看：`GET /api/capabilities`、`POST /api/snapshots`、目录及片段接口。错误为 `detail.code` 和 `detail.message`。
