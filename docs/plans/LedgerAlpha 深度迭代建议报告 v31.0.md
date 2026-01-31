# LedgerAlpha 深度迭代建议报告 v31.0

## 1. 深度反思与现状评估
在第 30 轮迭代中，我们成功上线了 `SentinelAgent` 税务哨兵并强化了 `AuditorAgent` 的审计逻辑。但在系统闭环和高级功能上，仍存在以下待优化空间：
- **知识灰度管理（F3.4.2）**：虽然 `KnowledgeBridge` 有 `GRAY` 状态，但缺乏自动化的“三审转正”逻辑。
- **银行流水模拟（F3.1.4）**：采集端（`Collector`）目前仅关注发票文件，缺乏对银行流水（CSV/Excel）的主动识别与处理，导致“影子预匹配”数据源单一。
- **经营洞察（F3.3.3/F3.3.4）**：`cashflow_predictor.py` 和 `exporter.py` 尚未深度整合，缺乏生成“投融资标准包”的自动化能力。
- **L2 推理链路（L2 Advanced Tier）**：`ManusWrapper` 仍需接入实际的 Web 搜索或高阶模型以应对 L1 低置信度场景。
- **数据穿透（F3.2.4）**：分录入库时未完整记录推理路径（Reasoning Path），导致“穿透式证据链”不完整。

## 2. 五项优化建议

### 建议 1：实现 `KnowledgeBridge` 的“三审转正”机制 (F3.4.2)
- **目标**：自动将通过 3 次审计的 `GRAY` 规则提升为 `VERIFIED`。
- **动作**：在 `KnowledgeBridge` 中增加 `promote_rules` 方法，并在 `AuditorAgent` 审计通过后累加命中次数。

### 建议 2：扩展 `Collector` 支持银行流水识别 (F3.1.2)
- **目标**：识别 CSV/Excel 格式的银行流水，并将其转化为 `pending_entries`（影子分录）。
- **动作**：修改 `Collector` 的后缀过滤与处理逻辑，增加 `BankStatementParser`。

### 建议 3：初步构建 `Exporter` 的投融资报告模版 (F3.3.4)
- **目标**：根据财务数据自动生成符合银行贷款标准的结构化 PDF/Markdown 报告。
- **动作**：在 `exporter.py` 中实现基于模版的报告生成逻辑。

### 建议 4：完善“穿透式证据链”记录 (F3.2.4)
- **目标**：在 `transactions` 表中增加 `inference_log` 字段，存储 OCR 及推理过程。
- **动作**：修改 `DBHelper` 架构并更新 `AccountingAgent` 的入库逻辑。

### 建议 5：实装 `ManusWrapper` 的 Web 搜索调研 (L2)
- **目标**：针对未知供应商自动执行 Web 搜索并获取经营范围。
- **动作**：在 `ManusWrapper` 中集成 `web_search` 接口。

---

## 3. 本轮执行计划 (Round 31)
1. **优化 `src/knowledge_bridge.py`**：实现灰度规则的命中统计与自动转正逻辑。
2. **升级 `src/collector.py`**：初步支持银行流水文件的识别与影子分录预转化。
3. **记录变更至 `docs/plans/优化迭代记录_Round31.md`**。
