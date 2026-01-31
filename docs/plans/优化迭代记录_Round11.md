# 优化迭代记录 - Round 11 (新阶段第一轮)

## 1. 优化建议 (Reflections)
根据对现有代码的深度扫描，提出以下 5 个优化点：

1.  **【MasterDaemon】健康监控升级**：目前仅依赖 `poll()` 检查进程存活。应增加对数据库 `sys_status` 表心跳时间的检查，识别“僵尸进程”（进程在但业务逻辑已卡死）。
2.  **【Collector】启动全量扫描**：`watchdog` 只能监听运行时的文件变动。程序启动时应自动扫描一次输入目录，确保在离线期间产生的单据不被遗漏。
3.  **【Collector】配置化 Worker 线程池**：将 `Collector` 中的线程数硬编码（目前为 2）提取到 `settings.yaml` 中，实现资源动态配置。
4.  **【DBHelper】增加连接存活检测**：虽然使用了 WAL 模式，但增加一个简单的 `ping` 或 `SELECT 1` 预检逻辑，可以进一步提升在高并发下的稳定性。
5.  **【Logging】统一日志脱敏格式**：在所有日志输出中强制执行脱敏过滤器，防止敏感文件路径或数据在日志中泄露。

## 2. 整改方案 (Rectification)
- 修改 `src/main.py` 以支持心跳超时检测。
- 修改 `src/collector.py` 增加 `initial_scan` 逻辑并接入配置中心。
- 更新 `src/db_helper.py` 的事务处理逻辑。
- 增强 `src/logger.py` 的过滤机制。

## 3. 状态变更 (Changes)
- [Done] **【MasterDaemon】**：实现了基于数据库心跳的健康检查逻辑（僵尸进程自动重启）。
- [Done] **【Collector】**：增加了启动时全量扫描逻辑，并接入 `settings.yaml` 配置线程数。
- [Done] **【DBHelper】**：新增 `check_health` 工具方法。
- [Done] **【Logging】**：引入 `PrivacyFilter` 自动脱敏绝对路径，并添加 `%(process)d` 辅助多进程调试。
- [Done] **【Config】**：更新 `settings.yaml` 增加了 `collector` 配置项。

## 4. 下一步计划
- 开始 Round 12：进一步强化 MatchEngine 的规则匹配精度。
