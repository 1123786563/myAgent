# 优化迭代记录 - Round 29

## 优化建议 (5点)
1. **AccountingAgent 性能优化**：引入 Exact Keyword Fast-Path，对简单关键词命中实现 O(1) 查找，减少正则开销。
2. **MasterDaemon 健康监控**：集成基于数据库心跳的逻辑健康检查，能够识别进程虽在但逻辑挂起的子服务并自动重启。
3. **DBHelper 自动维护**：增加每日一次的数据库完整性自检 (PRAGMA integrity_check)，确保长期运行的数据安全。
4. **系统性能监控**：在 MasterDaemon 心跳中集成 CPU/内存/线程数等基础指标采集，为后续性能调优提供数据支撑。
5. **基础设施增强**：抽象通用的性能计时装饰器 (`@timeit`) 和单例装饰器，提升代码开发效率与运行可观测性。

## 整改内容
- **src/accounting_agent.py**: 修改 `_load_rules` 和 `reply`，增加 `_keyword_map` 通道。
- **src/main.py**: 在 `run` 循环中加入逻辑健康检查 (`check_health`) 和指标采集 (`psutil`)。
- **src/db_helper.py**: 升级 `update_heartbeat` 接口，增加 `_daily_maintenance` 维护逻辑。
- **src/utils.py**: 新增文件，提供常用工具装饰器。
- **src/config_manager.py**: 补充 `health_timeout` 默认配置。

## 状态
- 代码已整改完成。
- 文档已更新。
- 准备进入下一轮迭代。
