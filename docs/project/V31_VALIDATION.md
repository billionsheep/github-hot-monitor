# v3.1 Skill 与工作台首屏验收

日期：2026-11-16。当前checkout从 `2072218` 增量修改，范围为技能规范、CLI适配层、工作台首屏与链接定位；本地实现及验收完成，本次通过main分支发布。既有v3标签、交付包与线上录制保留。

## 交付内容

- `skills/INDEX.md`：三工作流触发条件、输入Schema及统一调用/输出契约。CLI可解析该JSON索引；三个SKILL.md包含本机约束探测、调用示例、四态解释与Web复核规则，均通过技能格式检查。
- `python -m evidence.cli`：skills、inspect、run、result、replay五个命令。run复用现有快照/会话API；本机project只读探测Python声明、配置文件存在性及环境变量名称。stdout输出单行JSON，包含固定版本、结论、证据ID、复核标记和可打开的链接。
- 默认首页展示“RepoAudit 深度尽调工作台”，直接加载既有双仓架构录制的完整结果。品牌和主标题为“RepoAudit-Agent｜开源架构逆向、安全审计与选型工作台”，Hot Monitor保留为热门趋势候选池。
- 独立MCP安全预览读取原安全包，经原Hash/引用校验后呈现两条已有上下文复核。预览证据使用独立证据池，点击后显示MCP原文；不会混入双仓矩阵或改变报告。
- `?replay=文件名`、`?session=ID`、`?view=discover`分别定位录制、已有本机会话和趋势池；录制路径限定在原六份清单中。手机端优先结果列，图谱保留组件列表，问题/完整提交信息可展开。

## 实际验证

| 项目 | 结果 |
|---|---|
| 后端 | 144/144：原141项保留，新增3项技能/CLI测试 |
| 前端 | 25/25：原23项保留，新增默认首屏、来源隔离与深链接验证 |
| 离线契约 | 原16/16；多文件工具合同4/4，新结果仅存临时目录 |
| 静态构建 | 根路径及模拟Pages子路径 `/github-hot-monitor/` 均成功 |
| 浏览器 | 无参数自动显示两轮架构报告、2组关系图、6个回放入口、独立安全预览；原文来源匹配 |
| 手机 | 390×844，页面scrollWidth=390；图谱切换为列表，趋势池也无横向溢出 |
| CLI与实际API | 读取本机已有部署会话 `d4c99beacbd8443d9b9fbe7cf091ae58`，JSON链接打开同一两轮报告与配置块；追问控件正常可用 |
| 新会话调用 | HTTP替身验证health→快照→会话创建→状态读取契约，以及等待、读取失败和URL校验 |
| 模型调用 | 本次新增0次；没有重跑或改写原在线模型评测 |

本地静态服务器出现的 `/api/workflows`、`/api/health` 404为探测后切换静态模板的正常流程；页面无脚本异常。GitHub Pages主机模式由前端回归覆盖，不探测本机API。

## 保护文件核对

实施前记录 `eval/` 全部既有材料与 `web/replays/*.json` 哈希，共141个文件；完成后141/141一致，变化0。旧141项后端测试文件未修改。以下六份包保持逐字节不变：

| Replay | SHA-256 |
|---|---|
| agents-python-comparison.json | `e803625feb35e02d02eabed38d08624bcf3b1bd40ba42fa42fd598ee8b2014bc` |
| fastapi-python311.json | `2fa5ecce979d726c8fff75bf81c0ad4289997543ea0a1a4d4106002bd5945237` |
| pydantic-model-endpoint.json | `d0b5367fd1b694c979c2f0b0d9fe519e781c447da366c67d3d89647c76d50b06` |
| v3-architecture-gateway.json | `510d7d110ab89ec3918e648ae4c8fa7e7c9d03759aadaa67d4101c974df492d4` |
| v3-mcp-security-signals.json | `ea15cf8f25268e4628539937a460d3dfe63d5f60acb738137dda875d587ea3d6` |
| v3-pydantic-deploy-blueprint.json | `aed0e785a4a6feb7c0306dde291b90c7aa6dca2e482ec483340af88ad2645c4f` |

## 使用与学习入口

[技能索引](../../skills/INDEX.md) · [CLI实现](../../evidence/cli.py) · [运行说明](RUNBOOK.md)

本机预览：<http://127.0.0.1:8781/>。实时服务：<http://127.0.0.1:8775/>。预览进程关闭后按RUNBOOK重启。在线主地址更新为 <https://billionsheep.github.io/repoaudit-agent/>；默认首屏为工作台。直接打开部署回放：<https://billionsheep.github.io/repoaudit-agent/?replay=v3-pydantic-deploy-blueprint.json>。项目源码：<https://github.com/billionsheep/repoaudit-agent>。

[桌面首屏](images/v31-desktop.png) · [390px首屏](images/v31-mobile.png)

可做的小练习：在临时调用方项目的pyproject.toml中修改requires-python，运行inspect并比较JSON；观察传给run的约束如何与目标仓库证据区分。无需改动录制包或调用模型。
