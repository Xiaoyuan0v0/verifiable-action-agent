# 冻结数据说明

`source_manifest.json` 记录原文件 URL、commit、字节数和 SHA-256，以及规范化结果哈希。执行 `python scripts/prepare_data.py` 可离线重建；只有显式 `--download` 才访问公开上游。转换代码是复现依据。

- `raw/travel_train.jsonl`：TravelPlanner commit `e52c87f4ac348a3410c46dc3553c519db5ec5e23` 的 `database/train_ref_info.jsonl`。保留完整冻结文件，转换前 3 行为 194 条记录；课程使用历史 2022 年任务，不是当前报价。
- `raw/travel_fields.md`：同 commit 的字段说明。`derived/travel.json` 明示每房每晚、每人每段、每人单餐等教学单位；未知门票、其他餐费和市内交通不计成零。每条规范化记录保留来源指针。
- `raw/retail_db.json` 与 `raw/retail_policy.md`：τ²-Bench commit `7aad81c37a3a78b4ed3e4866769f851400c64415`。确定性选取真实存在于该合成快照的已送达 T 恤换色任务，连带 10 个用户、23 个订单、36 类商品，检查引用完整性。
- `derived/` 是规范化业务快照；运行时复制到每个 episode 的 `business.json`，课程案例变化只改副本。`eval/dev/cases.json` 描述覆盖层，不修改原始来源。

数据不用于真实交易；`mock` 使用固定模拟响应，仅用于离线检查。许可与归属见 [licenses/NOTICE.md](licenses/NOTICE.md)。
