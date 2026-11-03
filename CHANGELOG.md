# 更新说明

## 2026-11-03 — 实验一（travel 路线 A）

### 本次推送包含的提交

| 提交 | 内容 |
| --- | --- |
| `1cf990b` | 完成 travel Agent 主循环、工具分派与三条规则 |
| `e5ff26f` | 补齐 TR3 的 `unpriced`；重复调用判重键改为 `(ID, 工具名, 参数)` |
| `55302dd` | 非字符串工具名用 `repr` 规范化；被拒批次不记入已见调用 |

### 代码改动

- `agent/loop.py`：实现 `run()` 的完整闭环——请求模型、保留完整 assistant 消息、校验 `tool_calls`、按 `(ID, 工具名, 参数)` 判重、retail 批次约束、逐调用分派并回传观察、解析最终 JSON；格式纠正最多两次（`MAX_FORMAT_RETRIES=2`），预算/Provider 错误按规则终止。
- `tools/dispatcher.py`：实现 9 道关卡（ID/类型/白名单/参数 JSON/对象类型/schema），错误以结构化 `result` 返回。
- `domain_rules/travel.py`：实现 TR1/TR2/TR3 并在 `RULES` 注册；TR3 的 FAIL/UNKNOWN 分支均带 `unpriced`。
- `tests_student/travel/test_counterexamples.py`：新增 11 条反例（人数/房数、日期、城市、日程、容量、价格、类型、无效 ID）。

### 修复的问题

- **判重误杀**：旧实现只用调用 ID 判重，同 ID 换参数/换工具会被误判为重复。现按 `(ID, 工具名, 参数)` 判重；非字符串 `name/arguments` 用 `repr` 规范化，避免不可哈希导致 `TypeError`。
- **被拒批次污染判重集合**：`seen_calls.update()` 移到 retail 校验之后；整批拒绝的调用没有执行，模型修正后可用同一 ID 重发。
- **TR3 `unpriced` 缺失**：`plan` 不是对象等 FAIL 分支补齐 `unpriced`，保持返回结构一致。

### 验证结果

- `python -m unittest discover -s tests_infra` → 22 tests OK
- `python -m unittest discover -s tests_student/common` → 10 tests OK
- `python -m unittest discover -s tests_student/travel` → 16 tests OK
- `python -m app doctor` → infrastructure PASS；`student_todo_files: ["domain_rules/retail.py"]`（travel 路线 A，retail 未实现是预期行为）
- 六类 mock（`ds01_v2`、`ds_changed_v2`、`ds_missing_v2`、`ds_blocked_v2`、`ds_failure_v2`、`ds_limit_v2`）：`check_episode.passed=True`
- 两条最终 live：`live_final_01`（standard）COMPLETED，7 次模型/9 次工具，总额 1305.0；`live_final_02`（changed）COMPLETED，8/12，总额 1418.0；两条 `written == readback`
- 上述 episode 的 `summary.json` 中 `code_hashes` 与当前 HEAD 一致

### 说明

- 学习文档、报告与运行证据不在本仓库：`runs/`、`state/runtime/`、`reports/submission/` 由 `.gitignore` 排除。
- `config.local.json` 含真实 API Key，未提交。
