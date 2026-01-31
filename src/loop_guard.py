import os

class LoopGuard:
    def __init__(self):
        # 存储已访问路径的物理标识：(device_id, inode)
        self.visited_inodes = set()

    def is_safe(self, path):
        """
        检查路径是否从未访问过（防止软链接环路）
        """
        try:
            stat = os.stat(path)
            identity = (stat.st_dev, stat.st_ino)
            if identity in self.visited_inodes:
                return False
            self.visited_inodes.add(identity)
            return True
        except Exception:
            return False

    def clear(self):
        self.visited_inodes.clear()
