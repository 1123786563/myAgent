# 优化迭代记录 - Round 12

## 1. 优化建议 (Reflections)
本轮聚焦于对账引擎（MatchEngine）的精度与稳定性，提出以下 5 个优化点：

1.  **【MatchEngine】时间窗口限制**：目前的匹配仅基于金额和关键词。应引入 `time_window` 逻辑（例如：只匹配 3 天之内的单据），防止跨月或跨年的陈年错单被误匹配。
2.  **【MatchEngine】分批处理机制**：目前的 `run_matching` 会一次性读入所有 PENDING 数据。在数据量极大时会占用内存，应改为分批（Limit/Offset）处理。
3.  **【MatchEngine】引入对账权重得分**：目前是“全等即匹配”。应引入评分机制（金额完全一致 + 关键词部分匹配 = 100分，仅金额一致 = 60分），只有超过阈值才自动确认。
4.  **【MatchEngine】支持多币种转换预检**：如果系统涉及外币，目前直接比较 `amount` 会出错。应在匹配前增加币种检测逻辑（即使当前全为人民币，也应具备字段冗余）。
5.  **【MatchEngine】心跳补全**：更新 `MatchEngine` 以符合 `MasterDaemon` 的健康检查要求，在主循环中更新数据库心跳。

## 2. 整改方案 (Rectification)
- 修改 `src/match_engine.py` 引入分批处理、时间窗口和心跳逻辑。
- 在 `src/db_helper.py` 中补全相关的查询字段（如 `created_at`）。

## 3. 状态变更 (Changes)
- [Done] **【MatchEngine】时间窗口**：引入了基于 `created_at` 的 7 天对账过滤，防止跨期误配。
- [Done] **【MatchEngine】性能优化**：实现了 SQL 层的初步过滤和 Batch 处理（Limit 100），极大减少内存开销。
- [Done] **【MatchEngine】守护化**：改造成 `main_loop` 模式，并接入了数据库心跳。
- [Done] **【MatchEngine】鲁棒性**：关键词匹配增加了 `lower()` 处理，提高容错率。

## 4. 下一步计划
- 开始 Round 13：强化交互中心（InteractionHub），支持异步通知。
