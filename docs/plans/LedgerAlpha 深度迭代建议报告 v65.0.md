# LedgerAlpha 深度迭代建议报告 v65.0 (Round 25)

## 1. 深度反思与自评 (Self-Reflection)
在第 24 轮迭代中，我们实现了数据库损坏自愈、主动业务背景补全以及语义级对账。目前系统在架构稳健性和 HITL（人机协作）深度上表现优异。然而，站在“企业级多智能体基建”的角度，系统在**多租户数据隔离的底层逻辑**、**审计规则的动态版本控制**、以及**极端网络环境下的外部 API（如 OpenManus 外部调用）的降级策略**上仍可进一步夯实。此外，目前的 `ManagerAgent` 通信虽然有指纹，但缺乏“角色权限（Role）”的细粒度绑定。

## 2. 五大优化建议 (Top 5 Optimizations)

### 1. [Optimization 1] 通信协议的角色绑定 (RBAC-aware Messaging)
**问题：** 现有的 `LedgerMsg` 虽然包含 `sender`，但其内部通信不验证该 `sender` 是否具备执行特定 `action` 的角色权限。
**方案：** 升级 `bus_init.py`。在 `LedgerMsg` 中强制注入 `sender_role`，并在 `ManagerAgent` 路由时增加角色鉴权逻辑（如：只有 `AUDITOR` 角色能发出 `AUDIT_RESULT` 指令）。

### 2. [Optimization 2] 外部推理熔断与降级策略 (External AI Circuit Breaker)
**问题：** 当 OpenManus 外部 API 响应缓慢或失败时，可能导致整个工作流挂起。
**方案：** 在 `AccountingAgent` 路由逻辑中增加“熔断器”。若外部推理连续 3 次超时，自动降级为“规则匹配+人工标注”模式，确保核心流程不中断。

### 3. [Optimization 3] 审计规则版本化回溯 (Rule Versioning)
**问题：** `KnowledgeBridge` 更新规则后，旧规则被直接覆盖，无法回溯某笔历史账单是基于哪个版本的规则入账的。
**方案：** 升级 `knowledge_base` 表结构，增加 `version` 和 `valid_until` 字段。每次规则变更产生新版本，历史账单通过 `rule_version_id` 实现精准关联。

### 4. [Optimization 4] 多租户逻辑隔离支持 (Multi-tenant Foundation)
**问题：** 虽然目前是为单企业设计，但为了未来的 SaaS 化扩展，底层存储应预留租户 ID。
**方案：** 在 `transactions`, `knowledge_base`, `pending_entries` 等核心表中增加 `tenant_id` 字段，并在 `DBHelper` 的查询方法中默认注入 `tenant_filter` 装饰器。

### 5. [Optimization 5] 异步消息总线持久化 (Persistent Message Bus)
**问题：** 目前的 Agent 通信在内存中进行，若 MasterDaemon 崩溃，正在传输中的决策消息会丢失。
**方案：** 实现一个基于 SQLite 的轻量级 `Outbox` 模式。Agent 发出的关键指令先写入 `sys_outbox` 表，确认对方收到后再标记删除，确保消息“至少送达一次”。

---
**迭代记录：** v65.0 (Round 25) [2025-03-24]
