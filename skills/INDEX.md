# RepoAudit 渐进式技能索引

先根据下表选择一个工作流，再只读取该目录的 SKILL.md。三个技能复用现有引擎、预算、固定版本、检查点和证据校验。

| 工作流 | 触发条件 | 规范 |
|---|---|---|
| 架构研报 | 追踪入口、状态、模型接口与多仓架构差异。 | [arch_research](arch_research/SKILL.md) |
| 安全线索审计 | 复核进程执行、凭据读取、外连或文档指令覆盖线索。 | [sec_sentinel](sec_sentinel/SKILL.md) |
| 部署适配 | 核查目标仓库是否适合调用方的Python环境、容器与模型网关。 | [deploy_readiness](deploy_readiness/SKILL.md) |

以下 JSON 是 CLI `skills` 命令读取的契约。`repos` 是被调查的公开仓库；`project` 是调用方本地环境，两者证据不能混用。Python声明探测读取 pyproject.toml、.python-version；仅记录依赖/容器文件存在性及 .env.example 的变量名称，跳过符号链接、超限和解析失败文件，不读取 .env 或执行代码。

```json
{
  "schema_version": "1.0",
  "skills": [
    {
      "id": "arch_research",
      "name": "架构研报",
      "path": "arch_research/SKILL.md",
      "trigger": "追踪入口、状态、模型接口与多仓架构差异。",
      "boundary": "Python AST关系与规则线索，不推断未读取实现。"
    },
    {
      "id": "sec_sentinel",
      "name": "安全线索审计",
      "path": "sec_sentinel/SKILL.md",
      "trigger": "复核进程执行、凭据读取、外连或文档指令覆盖线索。",
      "boundary": "规则命中不是漏洞确认，报告必须说明上下文和覆盖缺口。"
    },
    {
      "id": "deploy_readiness",
      "name": "部署适配",
      "path": "deploy_readiness/SKILL.md",
      "trigger": "核查目标仓库是否适合调用方的Python环境、容器与模型网关。",
      "boundary": "配置示例需替换用户参数，安装和服务启动另按报告验证。"
    }
  ],
  "input_schema": {
    "type": "object",
    "additionalProperties": false,
    "required": [
      "workflow_mode",
      "repos"
    ],
    "properties": {
      "workflow_mode": {
        "type": "string",
        "enum": [
          "arch_research",
          "sec_sentinel",
          "deploy_readiness"
        ]
      },
      "repos": {
        "type": "array",
        "minItems": 1,
        "maxItems": 3,
        "uniqueItems": true,
        "items": {
          "type": "string",
          "description": "公开GitHub owner/repo或标准HTTPS仓库URL"
        }
      },
      "project": {
        "type": "string",
        "description": "调用方本机项目目录，只读探测根目录声明"
      },
      "query": {
        "type": "string",
        "minLength": 1,
        "maxLength": 1500
      },
      "base_url": {
        "type": "string",
        "default": "http://127.0.0.1:8773",
        "description": "仅本机HTTP服务根地址"
      },
      "wait": {
        "type": "number",
        "minimum": 0,
        "maximum": 600,
        "default": 300
      },
      "idempotency_key": {
        "type": "string",
        "maxLength": 100
      }
    }
  }
}
```

## 通用调用与输出

在本引擎仓库执行 `.venv/bin/python -m evidence.cli skills` 可获得索引JSON。命令的 `--workflow` 对应 `workflow_mode`；重复 `--repo` 对应 `repos`；`--base-url` 对应 `base_url`；其余同名参数使用连字符。未给 query 时使用引擎的统一场景模板。

- `inspect --project /absolute/project`：探测调用方声明，零模型调用。
- `run --workflow MODE --repo owner/repo --project /absolute/project`：创建固定版本快照、调用现有会话API，默认最多等300秒。实时执行使用服务端已有模型配置与预算。
- `result --session SESSION --base-url http://127.0.0.1:8773`：读取已创建会话；不会重复创建或继续模型调用。
- `replay --replay v3-architecture-gateway.json --workbench-url http://127.0.0.1:8781/`：从内置回放输出紧凑结果，零模型调用。

stdout 只输出一个紧凑JSON对象。报告字段包含 `session_id`、`workflow_mode`、`status`、`summary`、`rows`（四态、结论、下一步、证据ID）、`review_required`、`review_url`、`workbench_url`。有 FAIL / RISK / UNVERIFIED 或任务未完成时，必须向用户显示复核URL和对应项目；PASS也保留工作台链接。事实不足不得改写为FAIL，风险线索不得自动升级为漏洞。

退出0表示成功取得结果（不表示所有核查项PASS）；退出1表示输入或调用错误。`wait_expired=true` 时任务在服务端继续执行，使用 result 或 Web 查看，不重复提交。网络错误若未取得会话ID，先在 Web 历史会话确认状态，避免重复付费。idempotency_key绑定已创建的同组快照；CLI再次run会新建快照，不能代替result重试。

会话URL是 `?session=ID`，在对应本机服务中查看；录制URL是 `?replay=文件名`，在包含该录制的静态或本机工作台查看。Pages提供录制体验，实时核查由本机服务处理。

Claude Code / Cursor 可按工作流读取这些规范并运行CLI；不同IDE的技能注册方式由其配置决定。此目录不自动修改IDE或用户配置。运行入口与安装见 [RUNBOOK](../docs/project/RUNBOOK.md)。
