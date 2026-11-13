# Replay Bundle 1.0

UTF-8 JSON 对象：`schema_version` 为字符串 `"1.0"`；`payload_json` 为一个完整 JSON 对象的字符串；`sha256` 是 `payload_json` 原始 UTF-8 字节的小写 SHA-256。整个文件最大 5 MiB。用字符串承载内容可让 Python 与浏览器直接核对相同字节，不依赖 JSON 序列化器的键顺序。

`payload_json` 解析为对象：`recorded_at`（UTC ISO 8601）、`session`（公开会话详情，含 bindings、events、reports、usage）、`evidence`（以 evidence_id 为键的完整会话证据对象）、`traces`（公开工具轨迹）、`model`（仅模型名及推理强度的公开配置摘要）。不得包含凭证、隐藏推理或本机路径。事件按递增 ID 排列；固定版本使用完整 commit。

导入须校验包版本、5 MiB 上限、外层 SHA-256、各证据正文 SHA-256 与证据身份、仓库与 commit 均属于 session.bindings、GitHub HTTPS 来源链接属于对应仓库、所有报告引用存在且归属对应仓库与版本、摘录属于证据原文。校验失败则拒绝整包。Hash 是完整性校验，不是来源签名。

`web/replays/index.json` 为 `{ "schema_version": "1.0", "replays": [{ "title": "…", "path": "replays/example.json" }] }`。路径必须为站点内 `replays/` 相对路径。录制回放使用真实持久化会话导出，不伪造执行记录。
