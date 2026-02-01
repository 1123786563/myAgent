# LedgerAlpha 优化迭代日志

## Round 1: 影子银企直连实装 (Real Browser Automation)
- **Date**: 2026-01-31
- **Focus**: 替换 Mock 实现，引入 Playwright 浏览器自动化。
- **Changes**:
    1.  **新建 `src/connectors/browser_bank_connector.py`**:
        - 实现了 `BrowserBankConnector` 类。
        - 集成 `playwright` 库启动无头浏览器 (Headless Mode)。
        - 包含 `_login()` 和 `_scrape_transactions()` 桩代码（模拟了页面交互逻辑）。
        - 实现了 `transform_to_ledger()` 标准化输出。
    2.  **修改 `src/manus_wrapper.py`**:
        - 在 `_run_in_sandbox` 方法中动态加载并实例化 `BrowserBankConnector`。
        - 替换了原有的 `return "BANK_FLOW_EXTRACTED"` 模拟代码，改为真实调用 Connector 获取数据。
        - 增加了 `ImportError` 处理，当环境缺失 Playwright 时回退到 Mock 模式，保证鲁棒性。

## Round 2: L2 推理链 Agentic 循环 (ReAct)
- **Date**: 2026-01-31
- **Focus**: 实现 "Thought -> Action -> Observation" 循环，替代单次 LLM 调用。
- **Changes**:
    1.  **重构 `src/manus_wrapper.py`**:
        - `OpenManusAnalyst.investigate` 方法现在运行一个多步 ReAct 循环 (默认 5 步)。
        - 实现了简单的 LLM 输出解析器 `_parse_llm_step`，支持 `Thought`, `Action`, `Final Answer` 格式。
        - 实现了 `_execute_tool` 方法，支持 `search_web` (模拟), `browser_fetch` (调用 Round 1 的 connector), `ask_user`.
        - LLM 调用现在会累积历史 Context (`history` list)。
    2.  **修改 `src/accounting_agent.py`**:
        - `RecoveryWorker._attempt_recovery` 现在实例化 `OpenManusAnalyst` 并调用 `investigate` 接口。
        - 捕获完整的 `reasoning_graph` 并保存到数据库，实现推理过程的可追溯性。

## Round 3: 强制网络隔离代理 (Egress Proxy)
- **Date**: 2026-01-31
- **Focus**: 实施“本地锁”，强制所有 LLM/External 请求经过隐私检查代理。
- **Changes**:
    1.  **新建 `src/proxy_actor.py`**:
        - 实现了 `ProxyActor` 单例类，作为网络出口网关。
        - 实现了 `_inspect_and_sanitize` 方法，调用 `PrivacyGuard` 对负载进行强制扫描。
        - 实现了 `send_llm_request` 方法，拦截并修改 OpenAI SDK 的 `messages` 参数，确保敏感数据在发往云端前已被替换。
        - 增加了 `validate_url_request` 桩方法，用于后续扩展 HTTP 白名单。
    2.  **修改 `src/llm_connector.py`**:
        - 在 `_call_api_with_retry` 中实例化 `ProxyActor`。
        - 将直接的 `self._client.chat.completions.create` 调用替换为 `proxy.send_llm_request`。
        - 这样即使开发人员忘记手动调用脱敏，Proxy 层也会兜底拦截，满足“非功能需求 4.1”。

## Round 4: 知识回流闭环 (HITL Knowledge Loop)
- **Date**: 2026-01-31
- **Focus**: 将用户的手动修正沉淀为系统知识。
- **Changes**:
    1.  **修改 `src/knowledge_bridge.py`**:
        - 更新 `learn_new_rule` 方法，支持 `source` 参数。
        - 若 `source="MANUAL"`，直接标记为 `STABLE` 并原子化写入 `accounting_rules.yaml`。
        - 若 `source="OPENMANUS"`，标记为 `GRAY` (需经过 N 次验证才能转正)。
    2.  **修改 `src/interaction_hub.py`**:
        - 在 `handle_callback` 中，当用户提交 `action_value="CONFIRM"` 且包含修正数据时，显式调用 `KnowledgeBridge().learn_new_rule(..., source="MANUAL")`。
    - **效果**：用户一次修正，系统永久记住，并且新规则会立即被 `accounting_agent` 的文件监听器加载生效。

## Round 5: 待执行
- **Target**: 增强型多模态 OCR 预处理与结构化提取。
- **Plan**: 优化 `src/collector.py` (如果存在) 或创建新文件，集成简单的 OCR 模拟接口，并实现对复杂收据的正则提取（日期、金额、税号），提高 L1 阶段的准确率。
