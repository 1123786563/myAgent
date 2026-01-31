# LedgerAlpha 深度迭代建议报告 v33.0

## 1. 深度反思与现状评估
在 Round 32 中，我们升级了数据库底座（支持 `inference_log` 和 `transaction_tags`）并实现了投融资报告。目前系统在“三位一体”协作与穿透式管理方面仍有以下短板：
- **穿透式证据链实装 (F3.2.4)**：虽然数据库有了字段，但 `AccountingAgent` 尚未在入库时填充结构化的推理过程，导致“穿透”有名无实。
- **多维标签自动打标 (F3.2.3)**：缺乏根据语义自动打标签的逻辑，目前仅有表结构。
- **灰度规则优先级 (F3.4.2)**：`AccountingAgent` 在匹配规则时，尚未明确区分 `GRAY` 规则与 `VERIFIED` 规则的权重，可能导致冲突。
- **审计反馈回路 (Shadow Auditing)**：审计结果（`AuditorAgent`）尚未反哺到 `AccountingAgent` 的入库逻辑中，即：审计不通过时，分录状态应能联动回滚或标记风险。
- **成本看板指标缺失 (Non-Functional 4.2)**：`MasterDaemon` 监控了进程健康，但尚未在业务层面统计 Token 消耗与人工工时节省情况。

## 2. 五项优化建议

### 建议 1：实装 `AccountingAgent` 的穿透式推理路径记录 (F3.2.4)
- **目标**：确保每笔分录入库时，`inference_log` 字段包含：OCR 原始摘要、命中的规则 ID、置信度及处理时间。
- **动作**：修改 `AccountingAgent.reply` 的返回结构，使其包含详情，并由 `MatchEngine` 或相关 Actor 写入 DB。

### 建议 2：实现基于语义的多维自动打标 (F3.2.3)
- **目标**：根据分录内容自动识别并打上“项目”、“部门”标签。
- **动作**：在 `AccountingAgent` 中增加标签识别逻辑，并在 `DBHelper` 中提供批量写入 `transaction_tags` 的接口。

### 3. 建议 3：优化规则匹配的“审计权重”策略 (F3.4.2)
- **目标**：优先匹配 `VERIFIED` 规则，若命中 `GRAY` 规则，则自动调高审计级别。
- **动作**：重构 `AccountingAgent` 规则加载排序，引入 `audit_level` 权重。

### 4. 建议 4：完善 `MasterDaemon` 的成本与工时统计看板 (Non-Functional 4.2)
- **目标**：在 IM 端或日志中展示 AI 处理单据总数及节省的人工成本（按 5min/单计算）。
- **动作**：在 `MasterDaemon` 中汇总 `transactions` 的处理总数，并计算 `Human_Hours_Saved`。

### 5. 建议 5：实现审计结果的“入库阻断”联动 (F3.2.2)
- **目标**：当 `AuditorAgent` 判定为 `REJECT` 时，自动在 DB 中将该分录标记为 `RISK` 并不予生成正式凭证。
- **动作**：打通 `AuditorAgent` 与数据持久化层的负反馈回路。

---

## 3. 本轮执行计划 (Round 33)
1. **重构 `src/accounting_agent.py`**：支持输出结构化推理路径，并实现初步的标签识别逻辑。
2. **优化 `src/db_helper.py`**：新增 `add_transaction_with_tags` 接口。
3. **记录变更至 `docs/plans/优化迭代记录_Round33.md`**。
