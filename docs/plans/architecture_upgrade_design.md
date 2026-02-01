# 智能财务系统架构升级设计方案

> 生成日期：2026-02-01
> 状态：待实施

## 1. 概述

本设计文档旨在解决现有财务系统的业务缺失和技术缺陷，构建一个合规、智能、可扩展的企业级财务平台。

**核心目标：**
1. **合规性**：实现审计日志和审批流。
2. **完整性**：闭环对账流程，补全税务和多币种能力。
3. **稳定性**：引入异步任务队列和数据备份。
4. **可用性**：构建前端管理后台。

---

## 2. 总体架构图

```mermaid
graph TD
    User[用户] --> Frontend[React 管理后台]
    Frontend --> API[FastAPI 网关]

    subgraph "基础设施层"
        Auth[认证服务]
        Audit[审计日志]
        Notification[通知中心]
        TaskQueue[Celery 任务队列]
    end

    subgraph "核心业务层"
        Accounting[会计引擎]
        Invoice[发票服务]
        Reconciliation[对账引擎]
        Workflow[审批工作流]
        Tax[税务模块]
    end

    subgraph "数据存储层"
        PG[(PostgreSQL)]
        Redis[(Redis 缓存/队列)]
        S3[对象存储 (备份)]
    end

    API --> Auth
    API --> Accounting
    API --> Invoice
    API --> Reconciliation
    API --> Workflow

    Reconciliation --> TaskQueue
    Workflow --> Notification
    TaskQueue --> Redis
    Accounting --> PG
    Audit --> PG
```

---

## 3. 详细设计：基础设施阶段 (Phase 1)

### 3.1 审计日志 (Audit Logging)
*   **存储**：PostgreSQL `audit_logs` 表。
*   **机制**：SQLAlchemy Event Listeners 自动捕获 `User`、`Account`、`Transaction` 等关键模型的变更。
*   **表结构**：
    ```python
    class AuditLog(Base):
        id = Column(Integer, primary_key=True)
        user_id = Column(Integer, index=True)
        action = Column(String(50))  # create, update, delete, login
        resource_type = Column(String(50)) # table name
        resource_id = Column(String(50))
        changes = Column(JSONB)  # {"amount": {"old": 100, "new": 200}}
        ip_address = Column(String(50))
        created_at = Column(DateTime)
        tenant_id = Column(Integer)
    ```

### 3.2 异步任务队列 (Async Tasks)
*   **选型**：Redis + Celery。
*   **关键任务**：
    *   `send_notification_email`: 邮件发送（重试策略：指数退避）。
    *   `generate_monthly_report`: 月报生成。
    *   `daily_backup`: 每日数据库备份。
    *   `auto_reconcile`: 每日自动对账。

### 3.3 通知中心 (Notification)
*   **架构**：Pub/Sub 模式。
*   **适配器**：
    *   `FeishuAdapter`: 复用现有代码。
    *   `EmailAdapter`: 新增 SMTP 支持。
*   **用户偏好**：用户可配置接收渠道（如：审批消息->飞书，系统公告->邮件）。

### 3.4 数据备份
*   **策略**：每日凌晨 02:00 全量备份。
*   **实现**：`pg_dump` -> `gzip` -> 上传 S3/本地保留7天。

---

## 4. 详细设计：核心业务阶段 (Phase 2)

### 4.1 对账引擎 (Reconciliation Engine)
*   **策略**：规则主导 + AI 辅助。
*   **流程**：
    1.  **数据标准化**：将不同渠道（支付宝、银行）流水转换为统一 `BankStatement` 模型。
    2.  **规则匹配**：执行 `ReconciliationRule`（如：金额一致且备注包含订单号）。
    3.  **AI 分析**：对未匹配项，调用 LLM 分析语义相似度，生成置信度评分。
    4.  **人工确认**：高置信度自动通过，低置信度人工审核。

### 4.2 审批工作流 (Approval Workflow)
*   **模式**：数据驱动的状态机。
*   **模型**：
    *   `WorkflowDefinition`: 定义流程节点和流转条件。
    *   `WorkflowInstance`: 关联具体业务单据（id, current_node, status）。
    *   `WorkflowAction`: 审批记录（approver, action, comment）。
*   **特性**：支持串行审批、条件分支（金额 > X）。

### 4.3 税务管理 (Tax)
*   **功能**：
    *   维护 `TaxRate` 表。
    *   交易录入时，根据税率自动拆分 `amount` 为 `net_amount` 和 `tax_amount`。

---

## 5. 详细设计：扩展业务阶段 (Phase 3)

### 5.1 多租户 (Multi-tenancy)
*   **方案**：共享数据库，字段隔离 (`tenant_id`)。
*   **实现**：
    *   所有业务表添加 `tenant_id`。
    *   SQLAlchemy `Session` 层面注入过滤条件，防止跨租户查询。
    *   中间件解析 Token 获取当前 `tenant_id`。

### 5.2 多币种 (Multi-currency)
*   **方案**：双金额字段。
*   **改造**：
    *   所有金额涉及表增加 `currency` (String) 和 `local_amount` (Decimal)。
    *   新增 `ExchangeRate` 表，每日同步汇率。

---

## 6. 详细设计：前端实现阶段 (Phase 4)

### 6.1 技术栈
*   **框架**：React + Vite。
*   **UI 库**：Ant Design Pro（开箱即用的管理后台脚手架）。
*   **状态管理**：Zustand / React Query。

### 6.2 核心页面
*   **仪表盘**：现金流图表、待办事项。
*   **财务中心**：凭证管理、日记账、报表。
*   **对账中心**：流水导入、对账处理、差异调节。
*   **审批中心**：我的待办、我的申请。
*   **系统设置**：用户管理、权限配置、审计日志、通知设置。

---

## 7. 实施路线图

1.  **准备工作**：创建 git 分支，配置 Docker Redis。
2.  **Sprint 1 (基础)**：DB Schema 迁移（多租户/多币种字段），集成 Celery/Redis，实现审计日志。
3.  **Sprint 2 (核心)**：实现审批流引擎、对账引擎后端逻辑。
4.  **Sprint 3 (前端)**：搭建 React 项目，对接基础 API。
5.  **Sprint 4 (完善)**：补全税务、通知、备份，进行联调测试。
