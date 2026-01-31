# 优化迭代记录 - Round 27

## 1. 优化建议 (Reflections)
本轮聚焦于消息总线（BusInit/LedgerMsg）的安全性、结构化严谨性与链路追踪，提出以下 5 个优化点：

1.  **【LedgerMsg】强 Schema 校验**：目前的 `LedgerMsg` 仅是普通的 `Msg` 子类。应引入字段模板检查，确保所有 `action=PROPOSE_ENTRY` 的消息必须包含 `amount` 和 `category` 字段，防止下游 Agent 因数据缺失崩溃。
2.  **【LedgerMsg】消息指纹与防篡改 (Signature)**：在消息中自动计算并附加 `hmac_signature`。接收方校验签名，确保内部总线上的指令未被中间层意外篡改或注入。
3.  **【BusInit】动态模型热切换**：重构 `init_bus`。支持在不重启 AgentScope 引擎的情况下，通过更新 `settings.yaml` 动态切换 Agent 使用的模型版本（如从 mini 切换到强力版）。
4.  **【BusInit】消息过期与重放攻击防护**：在消息中增加 `timestamp` 字段，接收方丢弃时间差超过 60s 的“陈旧消息”，防止逻辑闭环中的循环重放。
5.  **【LedgerMsg】链路可视化支持 (Trace Parent)**：引入类似 OpenTelemetry 的链路标识，在消息中透传 `span_id`，以便在日志中能串联起“采集 -> 识别 -> 审计 -> 入账”的完整时序图。

## 2. 整改方案 (Rectification)
- 升级 `src/bus_init.py` 中的 `LedgerMsg` 实现。
- 在 `ManagerAgent` 中增加签名校验和时间戳检查。
- 为消息总线增加字段强类型检查。

## 3. 状态变更 (Changes)
- [Done] **【LedgerMsg】消息防篡改**：引入了基于 HMAC-SHA256 的消息指纹校验逻辑。
- [Done] **【LedgerMsg】重放防护**：增加了 60s 的消息过期窗口检查。
- [Done] **【LedgerMsg】结构化预检**：在消息创建阶段自动补全缺失的财务关键字段。
- [Done] **【BusInit】轻量化初始化**：优化了 AgentScope 的启动逻辑，移除了冗余的配置加载过程。

## 4. 下一步计划
- 开始 Round 28：优化数据导出模块（Exporter），支持 Excel 样式美化与公式自动注入。
