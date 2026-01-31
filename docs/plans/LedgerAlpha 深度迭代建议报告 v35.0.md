# LedgerAlpha 深度迭代建议报告 v35.0

## 1. 深度反思与现状评估
在 Round 34 中，我们修复了 `AuditorAgent` 的逻辑 Bug 并实现了 `MasterDaemon` 的业务工时统计。目前，系统在“自进化”和“穿透式管理”上已具备核心框架，但在实际业务闭环和推理深度上仍有提升空间：
- **灰度规则优先级与决策机制 (F3.4.2)**：`AccountingAgent` 加载规则时虽有优先级排序，但尚未针对 `audit_level`（GRAY vs VERIFIED）进行差异化推理策略设计。
- **多维标签自动归集 (F3.2.3)**：目前的自动打标逻辑（`R&D` 等）非常初级，尚未实现根据复杂的业务上下文（如科目 + 金额 + 供应商）进行复合打标。
- **穿透式证据链前端视图 (F3.2.4)**：数据库已支持 `inference_log`，但缺乏一个聚合视图来一键展现分录的“OCR -> Reasoning -> Auditing”全链路。
- **推理熔断与成本控制 (Non-Functional 4.2)**：目前统计了节省工时，但尚未落地针对单笔高成本推理的熔断机制。
- **异常补偿机制 (F3.4.3)**：系统支持快照回滚，但缺乏针对数据库并发锁死或事务失败的自动补偿重试逻辑。

## 2. 五项优化建议

### 建议 1：实现 `AccountingAgent` 的“灰度敏感”匹配策略 (F3.4.2)
- **目标**：确保新规则（GRAY）在命中时自动触发更高的审计置信度要求。
- **动作**：重构 `AccountingAgent.reply`，在命中 GRAY 规则时，在返回包中显式标记 `requires_shadow_audit: True`。

### 建议 2：增强多维核算标签引擎 (F3.2.3)
- **目标**：支持更复杂的语义打标，如“部门”、“地区”及“预算项”。
- **动作**：在 `AccountingAgent` 中引入 `TagEngine` 逻辑，基于关键词权重实现多标签自动归集。

### 3. 建议 3：构建 `DBHelper` 穿透式全路径视图 (F3.2.4)
- **目标**：提供聚合了分录、标签、推理日志及审计结果的统一数据接口。
- **动作**：在 `DBHelper._init_db` 中新增 `v_audit_trail` 视图。

### 4. 建议 4：落地推理成本熔断保护 (Non-Functional 4.2)
- **目标**：防止因复杂规则导致的 Token 消耗或推理时延失控。
- **动作**：在 `AccountingAgent` 中引入 `InferenceGuard`，记录单次匹配的时延，超时则强制降级至 L1 简单模式。

### 5. 建议 5：完善 `KnowledgeBridge` 的规则质量评估逻辑 (F3.4.2)
- **目标**：不仅是命中 3 次转正，还需考虑审计通过率。
- **动作**：在 `knowledge_base` 表中增加 `reject_count` 字段，若驳回率过高则自动废弃该灰度规则。

---

## 3. 本轮执行计划 (Round 35)
1. **优化 `src/db_helper.py`**：新增 `v_audit_trail` 视图，并为 `knowledge_base` 增加 `reject_count` 字段。
2. **重构 `src/accounting_agent.py`**：实装“灰度敏感”匹配逻辑与多标签引擎雏形。
3. **记录变更至 `docs/plans/优化迭代记录_Round35.md`**。
