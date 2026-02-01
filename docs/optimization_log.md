# LedgerAlpha 优化日志 (Optimization Log)

## [Cycle 1] - 2025-03-24 (Current Date)
### 优化目标
1. 解耦组件通信：将直接方法调用改为基于数据库事件的异步通信。
2. 增强 `InteractionHub`：实现真正的事件分发逻辑。
3. 完善 `Sentinel`：将硬编码的税务逻辑转移到配置和数据库中。

### 改进内容
- **Communication**: 
    - 修改 `MatchEngine` 和 `AccountingAgent`，使其不再直接调用 `InteractionHub`，而是向 `system_events` 表写入 `PUSH_CARD` 或 `EVIDENCE_REQUEST` 事件。
- **InteractionHub**: 
    - 重构 `PollingWorker`，使其能够识别并“处理”这些事件（模拟发送通知）。
    - 增加 `Notification` 表支持（通过 `DBInitializer`）。
- **Sentinel**:
    - 将 `vat_rate_general` 等硬编码值改为从 `tax_policies` 表动态读取（已部分实现，需全面覆盖）。

### 评估
- 解耦性：组件间不再有直接依赖，增强了系统的鲁棒性。
- 扩展性：通过事件表，未来可以轻松接入飞书、微信等真实通知渠道。
- 灵活性：税务政策调整无需修改代码。
