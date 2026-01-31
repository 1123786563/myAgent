# 优化迭代记录 - Round 17

## 1. 优化建议 (Reflections)
本轮聚焦于配置管理器（ConfigManager）的灵活性、健壮性及运维便利性，提出以下 5 个优化点：

1.  **【ConfigManager】单例热加载机制**：目前配置仅在启动时加载。应引入文件监控或定时检查逻辑，支持在不重启服务的情况下热更新配置（如调整线程数、阈值）。
2.  **【ConfigManager】环境变量注入支持**：为了支持生产环境部署，应允许通过环境变量（如 `LEDGER_DB_PATH`）覆盖 `settings.yaml` 中的配置，遵循云原生最佳实践。
3.  **【ConfigManager】强类型校验与 Schema 验证**：目前的配置加载是“弱类型”的。应增加 Schema 验证（或简单的 key 存在性校验），防止因配置文件写错单词导致的运行时崩溃。
4.  **【ConfigManager】多层级配置继承**：支持 `base_settings.yaml` + `prod_settings.yaml` 的组合模式，方便开发环境与生产环境共用大部分配置。
5.  **【ConfigManager】配置访问日志**：在调试模式下记录配置的读取行为，方便追踪配置来源（是默认值、文件值还是环境变量）。

## 2. 整改方案 (Rectification)
- 升级 `src/config_manager.py`，引入环境变量覆盖逻辑和配置校验。
- 优化合并逻辑，支持多层级深度合并。
- 增加热加载接口。

## 3. 状态变更 (Changes)
- [Done] **【ConfigManager】热加载支持**：引入了文件修改时间检查机制，修改 `settings.yaml` 后系统会自动识别并重新加载配置，无需重启服务。
- [Done] **【ConfigManager】深度合并算法**：重写了合并逻辑，现在支持无限层级的配置嵌套合并。
- [Done] **【ConfigManager】环境变量注入**：支持以 `LEDGER_` 为前缀的环境变量覆盖配置文件（如 `LEDGER_PATH_DB` 会覆盖 `path.db`），适配 Docker 等云原生部署环境。
- [Done] **【ConfigManager】并发安全**：增加了线程锁 `_lock`，确保在多线程环境下配置加载的原子性。

## 4. 下一步计划
- 开始 Round 18：重构规则解析器（AccountingRules），支持更复杂的逻辑判断（逻辑与/或）及正则表达式匹配。
