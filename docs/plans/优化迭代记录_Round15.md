# 优化迭代记录 - Round 15

## 1. 优化建议 (Reflections)
本轮聚焦于重试机制（RetryUtils）的精细化与工程化，提出以下 5 个优化点：

1.  **【RetryUtils】装饰器化实现**：将重试逻辑封装为 `@retry` 装饰器，方便在全项目（如 API 调用、数据库事务）中无侵入式复用，减少样板代码。
2.  **【RetryUtils】异常分类重试**：目前是无差别重试。应支持配置 `retry_on` 异常列表，仅针对网络抖动（Timeout/ConnectionError）或数据库锁定进行重试，避免在语法错误或逻辑错误上浪费资源。
3.  **【RetryUtils】引入抖动（Jitter）算法**：在指数退避的基础上增加随机抖动（Full Jitter），防止多个 Worker 在同一时间点集中重试导致系统“惊群效应”。
4.  **【RetryUtils】最大重试耗时上限**：除了重试次数，增加一个 `max_total_time` 参数，确保即使重试次数未满，总耗时超过预设阈值也必须停止，保证系统响应及时。
5.  **【RetryUtils】重试后置处理（Fallback）**：支持传入 `on_failure` 回调函数，在所有重试彻底失败后自动执行清理逻辑或触发报警通知。

## 2. 整改方案 (Rectification)
- 重写 `src/retry_utils.py` 为功能完备的重试库。
- 将新重试机制应用到 `src/match_engine.py` 或 `src/db_helper.py` 的关键位置。

## 3. 状态变更 (Changes)
- [Done] **【RetryUtils】装饰器化**：实现了 `@retry` 装饰器，支持异常过滤和最大重试次数配置。
- [Done] **【RetryUtils】引入 Full Jitter**：在指数退避基础上增加了随机抖动，有效避免了多 Worker 冲突。
- [Done] **【RetryUtils】后置回调**：支持 `on_failure` 参数，确保系统在重试彻底失败后有兜底方案。
- [Done] **【RetryUtils】代码精简**：利用装饰器极大减少了业务代码中分散的 `while` 重试循环。

## 4. 下一步计划
- 开始 Round 16：强化系统工具类（Utils），支持更安全的文件移动、MD5校验及大文件流式处理。
