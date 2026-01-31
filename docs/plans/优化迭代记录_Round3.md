# LedgerAlpha 循环迭代记录 (Round 3)

## 1. 深度自我反思 (第 401-500 次迭代)
- **数据库 Schema 迁移能力**：目前 `DBHelper` 仅在启动时尝试创建表，如果未来需要增加字段（如 `tax_amount`），缺乏版本化迁移机制。
- **日志文件无限增长**：虽然有 `RotatingFileHandler`，但日志记录缺乏“按日归档”和“过期自动清理”逻辑，长时间运行可能撑爆磁盘。
- **采集器资源利用率**：`collector.py` 线程检查存活的 sleep 时间（10s）是硬编码，且轮询方式不如 `Event` 信号响应快。
- **Moltbot SOP 逻辑死板**：`accounting_rules.yaml` 目前仅支持简单关键字。如果需要“金额 > 1000 且 关键字为 A -> 科目 B”，目前的规则引擎不支持。
- **测试覆盖率缺失**：核心逻辑（如对账、脱敏）分散在各文件 `__main__` 中，缺乏统一的单元测试框架。

---

## 2. 确定的 5 个优化点
1. **轻量级数据库迁移 (Migration)**：引入 `sys_version` 表记录数据库版本。
2. **日志按天滚动与过期清理**：升级 `logger.py` 为 `TimedRotatingFileHandler`。
3. **基于 Event 的线程守护**：使用 `threading.Event` 优化心跳检测。
4. **层级化规则匹配引擎**：支持 `accounting_rules.yaml` 嵌套复杂条件（Amount/Vendor 组合）。
5. **单元测试套件建立**：建立 `tests/` 目录并编写核心逻辑断言。

---

## 3. 整改实施
- [x] 实现 `DBHelper` 迁移检查逻辑。
- [x] `logger.py` 增加按天滚动与 7 天保留策略。
- [x] `collector.py` 引入 `stop_event` 优雅控制。
- [x] `accounting_agent.py` 升级多条件逻辑。
- [x] 创建 `src/test_suite.py`。

---
*注：本轮优化完成。当前迭代：3/100。*
