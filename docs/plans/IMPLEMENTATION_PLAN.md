# LedgerAlpha Implementation Plan

This document outlines the strategic roadmap to evolve LedgerAlpha from a functional PoC into a production-grade, commercial SaaS intelligent accounting platform.

## Phase 1: Foundation & Infrastructure
**Theme:** Stability, Scalability, and Security.

### 1.1 Database Migration (SQLite to PostgreSQL)
*   **Goal:** Enable high concurrency, JSONB support for flexible schemas, and row-level locking.
*   **Technical Approach:**
    *   Update `src/core/config_manager.py` to support PostgreSQL connection strings.
    *   Refactor `src/core/db_base.py` to use `psycopg2` driver via SQLAlchemy.
    *   Migrate existing `src/core/migrations/` logic to ensure data integrity during transfer.
    *   Enable `pgvector` extension if supporting local vector storage for RAG later.
*   **Definition of Done:** `docker-compose.yml` runs a Postgres container, the application connects successfully, and all integration tests pass against PG.

### 1.2 Multi-Tenancy Architecture
*   **Goal:** Support multiple organizations (SaaS model) with strict data isolation.
*   **Technical Approach:**
    *   **Data Layer:** Add `tenant_id` column to all `BaseModel` classes in `src/core/db_models.py`.
    *   **Middleware:** Implement `TenantMiddleware` in `src/auth/middleware/` to extract Tenant ID from JWT and set context.
    *   **Logic:** Update `db_helper.py` to automatically inject `filter(tenant_id=...)` into all queries.
*   **Definition of Done:** User A (Tenant X) cannot query or update any records belonging to User B (Tenant Y).

### 1.3 Asynchronous Task Queue (Redis + Celery)
*   **Goal:** Prevent API blocking during heavy operations (OCR, AI reasoning, Report generation).
*   **Technical Approach:**
    *   Deploy Redis via `docker-compose.yml`.
    *   Create `src/core/celery_app.py` for worker configuration.
    *   Refactor `src/engine/ocr_processor.py` and `src/agents/` to run as Celery tasks.
    *   Implement polling/webhook mechanism for frontend to get task status.
*   **Definition of Done:** Uploading a 50-page PDF invoice returns "202 Accepted" immediately, and processing occurs in background.

---

## Phase 2: Core Accounting & Compliance
**Theme:** Business Logic Completeness and Auditability.

### 2.1 Advanced Workflow Engine
*   **Goal:** Support complex, configurable approval flows (e.g., "Expenses > $5k need CFO approval").
*   **Technical Approach:**
    *   Refactor `src/engine/workflow_engine.py` to use a Finite State Machine (FSM) library (e.g., `transitions` or custom).
    *   Create `WorkflowDefinition` models to store rules in DB/YAML.
    *   Expose API endpoints for state transitions (`approve`, `reject`, `request_change`).
*   **Definition of Done:** A reimbursement request correctly transitions through `Draft -> Manager_Review -> Finance_Review -> Paid` based on configured rules.

### 2.2 Comprehensive Audit Logging
*   **Goal:** Full traceability of *who* changed *what* and *why* (critical for finance).
*   **Technical Approach:**
    *   Create `AuditLog` table in `db_models.py` (fields: `user_id`, `resource`, `action`, `before_snapshot`, `after_snapshot`, `timestamp`).
    *   Implement SQLAlchemy Event Listeners (`after_insert`, `after_update`) in `src/core/audit_listener.py` to automatically record changes.
*   **Definition of Done:** Changing an invoice amount generates an immutable log entry showing the old value and the new value.

### 2.3 Asset & Tax Modules
*   **Goal:** Fill the gap between "Cash Flow" and "Accrual Accounting".
*   **Technical Approach:**
    *   **Assets:** Create `src/accounting/asset_service.py` to handle fixed asset lifecycle and automatic depreciation entries.
    *   **Tax:** Implement `src/accounting/tax_engine.py` for VAT/GST calculation rules.
*   **Definition of Done:** System automatically generates a monthly depreciation journal entry for registered fixed assets.

---

## Phase 3: Intelligence & AI Evolution
**Theme:** Reliability, Learning, and Self-Correction.

### 3.1 RAG Knowledge Base (The "Brain")
*   **Goal:** Allow the AI to remember specific user preferences and historical corrections.
*   **Technical Approach:**
    *   Implement `KnowledgeBridge` in `src/core/knowledge_bridge.py`.
    *   Store vector embeddings of past valid Journal Entries.
    *   Update `src/agents/accounting_agent.py` to query the Knowledge Base for similar past transactions before making a decision.
*   **Definition of Done:** After a user manually corrects "Starbucks" from *Meals* to *Welfare* once, the AI automatically classifies the next Starbucks receipt as *Welfare*.

### 3.2 Confidence Scoring & Gray Rules
*   **Goal:** Handle uncertainty gracefully; Human-in-the-loop.
*   **Technical Approach:**
    *   Modify `src/infra/llm_base.py` to request confidence scores/logprobs.
    *   Implement logic: `If Confidence < 90% -> Status = NEEDS_REVIEW`.
    *   Create a "Review Queue" API for low-confidence items.
*   **Definition of Done:** Ambiguous invoices are not auto-posted but are flagged for human review with a specific reason ("Unsure about tax rate").

### 3.3 Self-Healing Data Pipeline
*   **Goal:** Robustness against "dirty" data.
*   **Technical Approach:**
    *   Enhance `src/engine/collector.py` with data validation and cleaning steps.
    *   Implement automatic retry strategies with "reflexion" (AI analyzes why it failed and retries with new params) for OCR failures.
*   **Definition of Done:** System gracefully handles and flags duplicate invoice uploads rather than crashing or creating double entries.

---

## Phase 4: Experience & Visualization
**Theme:** User Trust and Usability.

### 4.1 React Dashboard & Visualization
*   **Goal:** Provide clear visibility into financial health and system status.
*   **Technical Approach:**
    *   Initialize React project in `frontend/` with Ant Design Pro.
    *   Build standard accounting views: General Ledger, Income Statement, Balance Sheet.
    *   Create "AI Activity Log" component.
*   **Definition of Done:** User can view a graphical Cash Flow trend and drill down into specific days.

### 4.2 Interactive "Chain of Thought"
*   **Goal:** Build trust by showing *how* the AI reached a conclusion.
*   **Technical Approach:**
    *   Capture intermediate reasoning steps from `accounting_agent.py`.
    *   Store these steps in a structured format in the DB.
    *   Frontend displays a "Show Reasoning" button on journal entries.
*   **Definition of Done:** Clicking a transaction shows: "I extracted date X, identified vendor Y, found historical rule Z, therefore applied Account A."
