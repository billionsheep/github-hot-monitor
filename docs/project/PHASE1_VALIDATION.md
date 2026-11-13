# RepoAudit Phase 1 实施与验证记录

日期：2026-11-13（Asia/Shanghai）。状态：已通过主会话独立验收。

## 实现

- `evidence/config.py`：路径、超时、重试和读取上限；`schemas.py`：严格输入、不同来源的证据、类型化事实、覆盖和错误。
- `db.py`：`audit_engine.db` 的 SQLite WAL、`synchronous=NORMAL`、版本化迁移（当前版本 3）、可查询的快照/缓存/证据/会话关联/事件/用量字段与索引。事件和会话表为后续阶段准备，本阶段没有实现状态机或恢复。
- `github_client.py`：异步 HTTPX、有限重试、限流、绑定路径、树/文件缓存、Issue 搜索与评论截断。`tools.py`：六种只读工具及原文、树、大纲、元数据、Issue/评论证据。Issue 记录抓取时间、更新时间和调查时的 commit，不声称 Issue 属于该版本。
- `phase1_api.py`：公开快照创建、旧快照导入与六工具 API；执行工具前必须存在已登记的公开仓库和完整提交绑定。

## 真仓库联网检查

使用 `fastapi/full-stack-fastapi-template`、commit `aabb90126964a164e02aff39e7c385bb0598236d`，运行最终代码的六个 `/api/phase1/` 接口。`cache_hit` 是此次重复读取的结果；Issue 与仓库元数据是实时抓取。

| 工具 | 输入要点 | 实际结果 | 覆盖状态 |
| --- | --- | --- | --- |
| `overview` | 根目录 | 10 项事实、10 条证据；返回根及受限子目录 | 子目录超过 8 个，提示继续浏览；不完整 |
| `outline` | `README.md` | 1 项大纲事实、1 条索引证据 | 完整 |
| `lines` | `README.md`，L1–L20 | 1 条文件证据，重复读取命中缓存 | 完整 |
| `dependencies` | 默认发现目录 | 6 项事实、3 条证据；其中 `.python-version` 解析为 `3.14`，来源第 1 行 | 只检查所列目录，覆盖不完整 |
| `deployment` | 默认发现目录 | 108 项事实、100 条证据；包含 `compose.deploy.yml` 的代理端口 `80:80` 和 `443:443` | 相关文件超过 8 个且匹配项受限，明确截断 |
| `issues` | `docker`、`all` | 5 条 Issue 事实、11 条 Issue/评论证据 | 搜索和评论有截断，不能作为完整社区情况 |

以上六次均无工具错误。另以 `fastapi/fastapi` 的 `docker` / `all` 真实查询验证得到 5 条 Issue 和 17 条 Issue/评论证据；结果及评论截断均明确标记。未调用收费模型。

## 离线回归

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_frontend.js
git diff --check
```

结果：Python 58/58、前端 6/6 通过，差异检查通过。新增测试使用隔离 SQLite 和模拟 GitHub 响应，覆盖 Markdown 围栏与原始行号、AST/行块、单行/空文件/120 行与 6000 字符、路径和二进制、目录截断、限流/重试/分页、配置路径与原文位置、压缩 JSON、超长证据行、Issue/评论跨仓库、关键词限定符、重复观察、缓存损坏、并发证据写入、未登记提交和私有快照、备份迁移/回滚/并发导入、跨进程缓存读取。既有 R2 和网页测试一并通过。

## 迁移和兼容

已通过 SQLite 备份旧库到 `.evidence-data/evidence.sqlite3.pre-audit-41e9045fd55e44a3bb000fad7aa8a6fb.backup`，从备份读取并导入 10 个快照和 14 条缓存；检查备份完整性、文件缓存 SHA-256、导入记录及冲突。原 `.evidence-data/evidence.sqlite3` 保留；新库位于 `.evidence-data/audit_engine.db`，均不纳入 Git。每次显式导入会新建对应当次源状态的备份，重复导入幂等；冲突会回滚。

旧 `/api/snapshots`、`/api/agent` 与页面继续使用旧库和原有行为；在 8772 实测旧快照目录接口和 R2 配置接口均返回 HTTP 200，页面也返回 HTTP 200；显式导入让新工具可使用旧快照及缓存。两库没有自动双向同步，新创建的旧库快照需要再次显式导入；Phase 1 新工具也不会自动替换 R2 的两个旧工具。

## 格式与覆盖范围

确定性结构化项包括 `.python-version`、`pyproject.toml` 的 `project.requires-python` 与简单 Poetry 依赖、`package.json` / npm lock 的 engines 和依赖、requirements 行、Dockerfile 指令以及 Compose/YAML 的镜像、端口和环境标量；输出均绑定实际原文位置。TOML/JSON/YAML 同时进行安全解析；复杂 TOML 多行依赖、复杂 JSON 锁文件子树、YAML 锚点/变量展开的完整语义不保证提取，原文匹配行和覆盖说明供继续查看。`yarn.lock`、`go.sum` 为行索引；`setup.py` 与 Makefile 标记动态内容且不执行。Cargo、go.mod、其他锁文件只提供可解析的文本线索，不声称完整依赖图。SDK 声明不推断支持某个模型。

目录只自动检查根目录及有限常见子目录；聚合最多 8 个文件、每文件结构化和匹配各最多 12 条且总体原文字符受限。Issue 最多 5 条、每条最多 3 评论，单条正文不超过 6000 字符、总正文不超过 24000 字符；超限条目跳过并标记截断。截断、未查目录及解析错误均放入覆盖或错误；未列出不能推断不存在。

## 主会话独立验收

最终代码复跑结果：Python 58/58、前端 6/6、`git diff --check` 均通过。

审查过程中发现并要求修复了配置值误引用注释行、单行 JSON 漏读、并发存证唯一键冲突和新工具接口未校验已登记公开快照的问题。修复后独立重放原失败样例：TOML `>=3.12` 指向第 3 行真实赋值，压缩 JSON 的 engines / dependencies 可提取，12 个并发相同证据写入全部成功。相关回归已进入测试集。

另外用 HTTPX MockTransport 独立检查了新客户端的固定提交缓存、5xx 有限重试、超时有限重试、截断目录缺项保持未知，以及超过 512 KiB 时提前拒绝，全部通过。

独立真实 API 抽查 `fastapi/fastapi@5add7a458d629b07311d48261f696b5ac2bb9a5f`：

- 通过 `/api/phase1/snapshots` 注册公开快照后，依赖接口提取 `.python-version` 第 1 行的 `3.11` 与 `pyproject.toml` 第 12 行的 `>=3.10`。
- 13 条去重后的文件证据逐条校验了片段 SHA-256、仓库和固定提交；覆盖说明保留未查目录和匹配项限制。
- 对超过 150 行的 `pyproject.toml`，先直接读取时返回 `outline_required`；取行块索引后读取 L1–L20 成功，重复读取的证据 ID 相同且命中缓存。
- 浏览器打开 8772 页面，旧证据阅读入口与榜单仍可加载，新 Phase 1 路由出现在 OpenAPI 中。

验收结论：Phase 1 的持久化取证底座及六类工具可供 Phase 2 集成。复杂语言/锁文件的完整语义仍按上方格式范围处理；本阶段未将六工具接入 Lead-Sub，也未实现任务断点恢复或统一工作台。
