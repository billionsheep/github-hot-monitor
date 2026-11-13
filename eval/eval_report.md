# RepoAudit 评测报告

运行时间：2026-11-13T08:00:57.760268+00:00。模型：gpt-6.1-sol。

## 数据与评分

冻结集共 16 例：正常 4、文档与配置冲突 4、信息不足 3、伪造引用 3、注入 2。来源类型逐例记录，构造样本不指称真实项目缺陷。
离线检查来源/工具/护栏契约；在线使用真实模型，Rubric 0/1/2 分别表示状态不符、状态正确但关键证据缺失、状态和证据均符合。评分不覆盖自由文本的全部语义。

离线契约通过：16/16。
在线状态标签符合：11/13；状态及关键证据同时符合：11/13。

| 用例 | 类别 | 得分/2 | 实际状态 | 输入/输出 tokens | 全文基线得分 |
|---|---|---:|---|---:|---:|
| A1 | normal | 2 | PASS | 2986/381 | 2 |
| A2 | normal | 0 | 模型服务网络错误或超时。 | 5795/456 | — |
| A3 | normal | 2 | PASS | 4607/322 | 2 |
| A4 | normal | 2 | PASS | 4775/445 | 2 |
| B1 | contradiction | 2 | FAIL | 2852/384 | 2 |
| B2 | contradiction | 2 | FAIL | 4768/395 | 2 |
| B3 | contradiction | 2 | FAIL | 7093/702 | 2 |
| B4 | contradiction | 2 | FAIL | 4968/561 | 2 |
| C1 | missing | 2 | UNVERIFIED | 4939/627 | 2 |
| C2 | missing | 2 | UNVERIFIED | 9318/768 | 2 |
| C3 | missing | 0 | FAIL | 4910/576 | 2 |
| E1 | injection | 2 | FAIL | 2828/338 | 2 |
| E2 | injection | 2 | PASS | 4763/385 | 2 |

## 全流程成本比较

同模型、同问题、同冻结资料，配对 12 例：Lead/Sub 全流程 64691 tokens；全文单轮基线 23870 tokens；总 token 节省率 -171.01%。
基线将已选资料一次性给模型；harness 包含规划、取证和汇总的全部请求。负值表示本小样本中多轮编排消耗更多。

## 未通过案例

- A2：模型服务网络错误或超时。；实际状态 INTERRUPTED。
- C3：status_mismatch；实际状态 FAIL。
失败案例保留在分母中；网络中断前的已知 usage 仍计入账本，未返回用量的调用保留预算预留。状态标签与正文解释需同时复核。

## 复现与原始记录

离线：python eval/run_eval.py；在线：python eval/run_eval.py --online --baseline --max-usd 3。

源文件哈希：ccbc6379b216c8b83d04d586d57024450d2ceea7364038dd92c9b5491d97f22f。逐例结果见同目录 JSON；保留失败与低分。

实际请求数 78，usage 输入 84949、输出 9863、缓存输入 0 tokens；保守费用估算 USD 0.311002，未知调用预留 USD 0.026475。
按标准处理档及输入 USD 2.50/M、输出 USD 10/M 估算，账户账单为实际结算依据。[官方模型价格](https://developers.openai.com/api/docs/models/gpt-6.1-sol)（2026-11-13 核对）。

## 中断恢复补验

A2 使用同一检查点从 INTERRUPTED 恢复为 COMPLETED，标签和关键证据评分 2/2；未新增模型调用，保留 1 次未知调用和确定性汇总提示。首轮 11/13 的计数保持不变。详见 [recovery_results.json](recovery_results.json)。
