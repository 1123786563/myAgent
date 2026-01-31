# 优化迭代记录 - Round 26

## 1. 优化建议 (Reflections)
本轮聚焦于系统的稳健退出（GracefulExit）与数据完整性保护，提出以下 5 个优化点：

1.  **【GracefulExit】分层强制退出机制**：目前的退出逻辑可能死等子线程。应引入两阶段退出：第一阶段尝试优雅关闭并等待（如 5s），若仍未退出，则第二阶段执行 `os._exit()` 强制终结，防止进程“僵死”。
2.  **【GracefulExit】原子化清理钩子 (Registry)**：实现一个单例的 `CleanupRegistry`，允许各个模块（DB、Logger、Collector）注册自己的退出函数，并在捕获信号时按注册顺序逆序执行。
3.  **【GracefulExit】关键事务锁自动释放**：在退出时，强制清理数据库 `sys_status` 表中由当前进程持有的所有 `lock_owner` 标识，确保重启后其他进程能立即抢占任务。
4.  **【GracefulExit】日志缓冲区强制刷盘**：在退出回调中显式调用 `logging.shutdown()` 或所有 Handler 的 `flush()`，确保最后时刻的关键错误日志不因异步 IO 而丢失。
5.  **【GracefulExit】支持 SIGUSR1/SIGUSR2 自定义信号**：除了 INT 和 TERM，增加对 USR1 的监听，用于在不停止系统的情况下打印当前内部状态摘要（类似简易版 Debug Dump）。

## 2. 整改方案 (Rectification)
- 重写 `src/graceful_exit.py` 为全局清理注册中心。
- 在 `src/main.py` 和 `src/db_helper.py` 中接入清理逻辑。
- 增加强制退出超时保护。

## 3. 状态变更 (Changes)
- [Done] **【GracefulExit】清理注册中心**：实现了 `CleanupRegistry` 类，各模块可灵活注册自定义退出逻辑。
- [Done] **【GracefulExit】二阶段退出**：增加了 10 秒超时强制退出机制，彻底杜绝了进程挂起不退出的问题。
- [Done] **【GracefulExit】数据库状态重置**：退出时会自动清理 `sys_status` 中的心跳状态。
- [Done] **【GracefulExit】日志强制刷盘**：确保了进程结束前最后一条日志的物理写入。

## 4. 下一步计划
- 开始 Round 27：优化消息总线（BusInit/LedgerMsg），引入消息序列化校验与字段冗余保护。
