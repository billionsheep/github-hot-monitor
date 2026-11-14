# 运行与复现

当前主入口是统一 RepoAudit 工作台。旧 R1/R2 接口保留兼容；旧阶段文档中的端口是当时验收记录。

## 安装与本机配置

```bash
cd '/Users/moon/Documents/ai agent/github-hot-monitor'
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp -n .env.example .env.local
chmod 600 .env.local
```

已有虚拟环境可以直接安装依赖。用文本编辑器打开 `.env.local`，填写：

```dotenv
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-6.1-sol
LLM_API_KEY=在本机填写
LLM_API_FORMAT=responses
LLM_REASONING_EFFORT=low
```

配置由服务端读取，网页不会接触密钥。`.env.local` 与 `.evidence-data/` 已排除 Git。启动脚本优先使用环境中的 `GITHUB_TOKEN`，否则尝试已有 `gh` 登录；没有登录时用匿名 API。

## 启动实时工作台

```bash
python3 ops/scripts/start_local.py
```

默认 <http://127.0.0.1:8773/>，API 文档 <http://127.0.0.1:8773/docs>。换端口：`python3 ops/scripts/start_local.py --port 8774`。Ctrl+C 停止服务。脚本先重建 `public/`，再启动服务；源码修改后重新启动。

1. 在“发现”选择项目并加入对比，或在“尽调”输入公开 GitHub 仓库。
2. 选择架构研报、安全线索审计或部署适配，填写具体问题，点击“开始尽调”；每个仓库固定到当时的完整提交。
3. 查看逐项矩阵、执行轨迹和原文；完成后可追问及导出 Markdown / Replay JSON。
4. 刷新页面会恢复最近会话，也可从历史列表重新打开。恢复与追问继续使用原提交，新建会话才刷新版本。

当前每轮总预算最多 20 次模型、24 次工具、60,000 输入 / 16,384 输出 tokens；每仓 Sub 最多 6 次模型、8 次工具，Lead 最多 2 次模型。达到预算保留证据并给出缺口。实时执行会产生模型费用，页面显示实际 usage。

## 静态回放

```bash
python3 ops/scripts/build_pages.py --state-dir data --web-dir web --out-dir public
python3 -m http.server 8781 --bind 127.0.0.1 --directory public
```

访问 <http://127.0.0.1:8781/>，在“尽调”的录制回放中选择案例。支持播放、暂停、重播、跳到结果和证据查看，也可导入自己导出的 JSON。静态模式禁用实时任务，无需 API 密钥。

回放包上限 5 MiB，载入时核对包和片段哈希、证据身份、固定版本、引用及来源地址。格式见 [REPLAY_BUNDLE_SCHEMA.md](REPLAY_BUNDLE_SCHEMA.md)。分享时提供整个 `public/` 或通过已有 Pages 工作流发布。

## 数据与恢复

`.evidence-data/audit_engine.db` 保存快照、缓存、证据、会话检查点、公开事件、模型用量和工具回执。采用 SQLite WAL 短事务；停止服务后再备份整个 `.evidence-data/`。旧 `evidence.sqlite3` 只用于历史 R1/R2 兼容，可通过 `/api/phase1/import-legacy` 先备份再导入。

服务意外退出时，已提交工具回执可复用。旧执行租约最长约 180 秒；到期后在历史会话中恢复。若模型响应在写入检查点前丢失，该请求保留为未知用量，恢复可能再次调用；这项边界由故障测试和用量账本记录。

## 测试与评测

```bash
.venv/bin/python -m unittest discover -s tests -q
node --test tests/test_*.js
.venv/bin/python tests/phase2_crash_smoke.py
.venv/bin/python eval/run_eval.py
```

v3 离线多文件合同：`.venv/bin/python eval/v3_tool_cases.py`。实际在线记录见 [v3 实测报告](../../eval/v3/eval_report.md)。

复做收费评测使用 `.venv/bin/python eval/run_v3_eval.py --batch regression`，成本对照使用 `--batch comparison`。这些脚本共用 `.evidence-data/v3-budget.json` 的5美元账本，已发生调用继续累计。普通运行入口使用轮次预算；本次验收的额外美元总预算由 `eval/v3_preview.py` 和评测适配器执行。

## 常见情况

| 表现 | 处理 |
|---|---|
| 显示静态模式 | 使用上述启动脚本，确认 `/api/health` 可访问 |
| 模型未配置 / 401 | 检查本机 API 密钥及项目权限，然后刷新 |
| GitHub 限流 | 使用已有 `gh` 登录启动，或等待返回的额度恢复时间 |
| 恢复提示执行权被占用 | 等待返回的 `retry_after`，避免重复启动 |
| UNVERIFIED | 打开证据与覆盖信息；缩小问题或补充文件路径后追问 |
| 配置存在但需要运行验证 | 工具读取静态资料；按报告建议在自己的环境安装测试 |
| 端口占用 | 访问已有进程，或用 `--port` 换端口 |

`build_pages.py` 会重建输出目录，始终将 `--out-dir` 指向可再生的 `public/`。

## 三工作流与扫描范围

- 架构研报：输入关注的文件或参数，例如 `base_url`，系统先生成 AST/规则索引，再按完整语句补查。SVG 图边和组件列表均可打开证据；手机显示列表。
- 安全线索审计：可限定仓库内目录。每次扫描最多尝试24个目录、24个文本文件、累计读取1MiB，单文件最多512KiB。报告显示覆盖范围、截断原因和继续位置；规则命中与上下文复核分开展示。
- 部署适配：判断版本、容器和模型配置条件；有原文支持时输出可复制的 Python 字面量配置、JSON 或环境变量配置，附用户自填项与验证步骤。

追问继承当前工作流和固定提交；切换工作流后开始会创建新会话。新导出 Replay 为2.0，继续读取旧1.0，原三份回放保留。
