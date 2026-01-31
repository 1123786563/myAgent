# 优化迭代记录 - Round 16

## 1. 优化建议 (Reflections)
本轮聚焦于基础工具库（Utils）的安全性、可移植性及文件处理能力，提出以下 5 个优化点：

1.  **【Utils】原子化文件移动**：目前的系统在处理单据时可能涉及文件移动。应实现 `atomic_move`，在跨文件系统移动时使用“临时文件+重命名”策略，确保单据移动过程中不损坏。
2.  **【Utils】哈希算法升级 (BLAKE3/SHA3)**：MD5 已不再安全。应支持 `SHA256` 作为默认全量哈希，并为快速哈希增加 `xxhash` 或更健壮的逻辑，防止哈希碰撞导致的单据丢失。
3.  **【Utils】敏感路径清理工具**：提供一个统一的 `sanitize_path` 方法，处理 Windows/Linux 路径分隔符差异，并自动剔除路径中的潜在危险字符。
4.  **【Utils】大文件流式读取优化**：优化 `calculate_file_hash`，统一所有文件操作的 `chunk_size` 到 128KB，以获得更好的 I/O 性能。
5.  **【Utils】单据内容预检（Magic Number）**：增加基于文件头（Magic Number）的文件类型校验，而不仅仅依赖后缀名，防止伪造的单据文件进入系统。

## 2. 整改方案 (Rectification)
- 重写 `src/utils.py`。
- 为 `calculate_file_hash` 增加文件头校验逻辑。
- 实现 `atomic_move` 工具函数。

## 3. 状态变更 (Changes)
- [Done] **【Utils】文件原子操作**：实现了 `atomic_move`，确保单据在归档或移动时绝不损坏。
- [Done] **【Utils】安全校验升级**：新增了基于 Magic Number 的文件头校验，防止用户通过修改后缀名绕过安全检查。
- [Done] **【Utils】哈希性能与安全**：全量哈希升级为 SHA256，并统一了 128KB 的 I/O 缓冲区。
- [Done] **【Utils】错误处理**：增加了详细的日志记录，方便排查文件读写冲突。

## 4. 下一步计划
- 开始 Round 17：优化配置管理器（ConfigManager），支持环境感知（Dev/Prod）及热加载机制。
