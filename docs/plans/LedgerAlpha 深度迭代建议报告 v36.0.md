# LedgerAlpha 深度迭代建议报告 v36.0

## 1. 深度反思与现状评估
在第 35 轮迭代中，我们实装了“灰度敏感”匹配逻辑，并构建了穿透式全路径视图 `v_audit_trail`。目前系统在自进化闭环的“负反馈”处理上仍显薄弱：
- **灰度规则惩罚机制 (F3.4.2)**：目前仅有命中计数（`hit_count`），虽然数据库增加了 `reject_count`，但 `KnowledgeBridge` 尚未实现基于驳回次数的“自动降级”或“废弃”逻辑。
- **审计反馈回路不完整 (Shadow Auditing)**：`AuditorAgent` 的驳回结果目前只更新了 `knowledge_base` 的风险等级，尚未联动触发 `KnowledgeBridge` 累加驳回计数。
- **穿透式视图性能 (F3.2.4)**：随着数据量增加，`v_audit_trail` 使用 `GROUP_CONCAT` 可能会产生性能瓶颈，且缺乏对“审计时间线”的明细展示。
- **规则淘汰策略缺失 (F3.4.2)**：`cleanup_stale_rules` 仅基于时间和命中数，未考虑审计失败率这一关键质量指标。
- **配置校验不严 (L1)**：规则转正同步到 YAML 时，缺乏对科目编码合法性的最终校验，存在坏规则污染 SOP 库的风险。

## 2. 五项优化建议

### 建议 1：实装 `KnowledgeBridge` 的“优胜劣汰”算法 (F3.4.2)
- **目标**：基于审计通过率动态管理灰度规则。
- **动作**：新增 `record_rule_rejection` 方法累加驳回数；当 `reject_count > 2` 时自动将 GRAY 规则标记为 `FAILED` 并禁止匹配。

### 建议 2：打通 `AuditorAgent` 到 `KnowledgeBridge` 的负反馈回路 (F3.2.2)
- **目标**：审计驳回时自动处罚对应的灰度规则。
- **动作**：修改 `AuditorAgent`，在识别到命中灰度规则且审计驳回时，调用 `KnowledgeBridge.record_rule_rejection`。

### 建议 3：增强 YAML 同步的安全校验 (L1)
- **目标**：防止非法规则污染本地规则库。
- **动作**：在 `_sync_to_yaml` 前增加科目编码格式校验（正则匹配 `\d{4}-\d{2}`）。

### 建议 4：扩展 `v_audit_trail` 视图字段 (F3.2.4)
- **目标**：展示更精细的审计时间线与风险分。
- **动作**：更新视图，加入 `audit_score` 和 `risk_score` 的展示（需先在 `transactions` 表补齐对应统计字段）。

### 建议 5：完善 `cleanup_stale_rules` 逻辑 (F3.4.2)
- **目标**：清理高质量但已失效，或低质量频繁报错的规则。
- **动作**：增加对 `audit_level = 'FAILED'` 规则的定期清理。

---

## 3. 本轮执行计划 (Round 36)
1. **优化 `src/knowledge_bridge.py`**：实现 `record_rule_rejection` 逻辑与转正安全校验。
2. **优化 `src/auditor_agent.py`**：在审计驳回时联动触发规则处罚机制。
3. **记录变更至 `docs/plans/优化迭代记录_Round36.md`**。
