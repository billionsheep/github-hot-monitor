# RepoAudit-Agent · GitHub Hot Monitor

面向开源框架调研和引入决策的证据核查工作台。提供架构研报、安全线索审计、部署适配三种工作流，支持1～3个仓库顺序调查与比较。

**使用流程：发现项目 → 加入候选 → 输入约束 → Agent 取证 → 比较矩阵 → 打开原文 → 追问 → 导出报告与回放。**

- Lead 拆解共同问题，每仓 Sub 使用独立上下文和八类只读工具；简单单仓部署核查走确定性快速路由。
- Python AST 定位参数与完整调用语句；有界扫描输出源码关联图、安全线索与覆盖缺口，配置示例可复制并附验证步骤。
- 文件绑定完整 commit；证据保留原始行号、SHA-256、抓取时间和固定版本链接。
- SQLite WAL 保存状态、证据、工具轨迹和用量，支持检查点恢复、历史会话与多轮追问。
- SSE 展示公开执行状态，原生页面提供矩阵与证据抽屉；真实录制可在纯静态站点播放。
- 保留原有热门榜单、搜索、专项评分与 GitHub Pages 构建。

技术栈：Python 3.11、FastAPI、Pydantic v2、HTTPX、SQLite WAL、OpenAI Responses / Function Calling、原生 HTML/CSS/JavaScript。

## 启动

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp -n .env.example .env.local
chmod 600 .env.local
```

在本机编辑 `.env.local` 的 `LLM_API_KEY`；默认官方 OpenAI、`gpt-6.1-sol`、low。随后：

```bash
python3 ops/scripts/start_local.py
```

打开 <http://127.0.0.1:8773/>。脚本自动构建，存在本机 `gh` 登录时读取 GitHub 凭证。密钥和运行数据库均留在本机。

## 无 API 演示

```bash
python3 ops/scripts/build_pages.py --state-dir data --web-dir web --out-dir public
python3 -m http.server 8781 --bind 127.0.0.1 --directory public
```

打开 <http://127.0.0.1:8781/>，进入“尽调 → 录制回放”，播放真实会话、比较结果、打开原文。回放不调用模型。

## 文档与验证

- [版本基线](docs/project/RELEASE_BASELINE.md)：v3 `repoaudit-v3-demo-2026-11-14`，保留 v2 基线
- [交付现状与验收](docs/project/DELIVERY_STATUS.md)
- [五分钟演示与交付指南](docs/project/DELIVERY_GUIDE.md)
- [安装、运行与排障](docs/project/RUNBOOK.md)
- [代码走读与学习练习](docs/project/CODE_GUIDE.md)
- [v3 实测评测报告](eval/v3/eval_report.md) · [评测协议](eval/README.md)
- [可用于简历的项目经历](docs/project/RESUME_PROJECT.md)
- [阶段计划和设计依据](docs/project/PROJECT_PLAN.md)

```bash
.venv/bin/python -m unittest discover -s tests -q
node --test tests/test_*.js
.venv/bin/python tests/phase2_crash_smoke.py
.venv/bin/python eval/run_eval.py
```

前三项验证代码与故障恢复，最后一项验证16个冻结证据契约。v3在线评测按 [预算清单](eval/v3/BUDGET_PLAN.md) 和 [评测入口](eval/README.md) 使用共享账本；CI运行免费检查。

## 榜单采集与发布

```bash
python3 ops/scripts/github_hot_monitor.py scan --state-dir data --top 20
```

榜单使用最近候选、元数据和启发式评分；首次采集没有历史增长速度。配置 `GITHUB_TOKEN` 可提高 API 额度。工作流 `.github/workflows/pages.yml` 每六小时扫描并构建，推送后通过测试才发布静态页面；实时 Agent 在本机运行。
