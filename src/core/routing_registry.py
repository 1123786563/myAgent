from infra.logger import get_logger
import time

log = get_logger("RoutingRegistry")

class RoutingRegistry:
    """
    [Optimization 1] 动态路由注册表：支持自学习 Hand-off (F3.1.4)
    管理 L1 (Moltbot) 与 L2 (OpenManus) 之间的任务分发。
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RoutingRegistry, cls).__new__(cls)
            cls._instance._init_registry()
        return cls._instance

    def _init_registry(self):
        # 专家词库
        self.expert_topics = {
            "股权激励", "递延所得税", "合并报表", "商誉减值", "研发加计扣除", "政府补助"
        }
        
        # [Optimization 5] 行业敏感关键词库 (Sector-Aware)
        from core.config_manager import ConfigManager
        self.sector = ConfigManager.get("enterprise.sector", "GENERAL")
        
        # 针对特定行业的专家级强制路由关键词
        self.sector_expert_kws = {
            "SOFTWARE": ["云服务器", "CDN", "算力集群", "中间件"],
            "MANUFACTURING": ["原材料", "半成品", "制造费用", "模具"],
            "RETAIL": ["损耗", "过期", "赠品", "SKU"]
        }

        # 供应商处理历史
        self.vendor_stats = {}
        # 强制路由冷却池：vendor_name -> expire_ts
        self.forced_l2_vendors = {}
        # [Optimization 1] 外部推理熔断器状态缓存
        self._last_circuit_check = 0
        self._is_circuit_broken = False

    def check_circuit_breaker(self):
        """[Optimization 1] 检查推理熔断器状态"""
        if time.time() - self._last_circuit_check > 60:
            from core.config_manager import ConfigManager
            self._is_circuit_broken = ConfigManager.get("circuit.accounting_external", False)
            self._last_circuit_check = time.time()
        return self._is_circuit_broken

    def get_route(self, content, vendor=None, l1_confidence=1.0):
        """
        根据内容、供应商及历史表现决定路由路径
        """
        # [Optimization 1] 熔断器拦截：若已熔断，禁止升级 L2
        if self.check_circuit_breaker():
            log.info("熔断器开启：强制保持在 L1 层执行降级处理。")
            return "L1-DEGRADED"

        # 0. [Optimization 5] 行业敏感词路由
        sector_kws = self.sector_expert_kws.get(self.sector, [])
        for kw in sector_kws:
            if kw in content:
                log.info(f"路由决策: 匹配 [{self.sector}] 行业敏感词 [{kw}] -> 强制升级至 L2。")
                return "L2-OpenManus"

        # 1. 冷却池预检
        if vendor and vendor in self.forced_l2_vendors:
            if time.time() < self.forced_l2_vendors[vendor]:
                log.info(f"路由决策: 供应商 [{vendor}] 处于 L2 强制保护期，跳过 L1。")
                return "L2-OpenManus"
            else:
                del self.forced_l2_vendors[vendor]

        # 2. 专家话题路由
        for topic in self.expert_topics:
            if topic in content:
                log.info(f"路由决策: 匹配专家话题 [{topic}] -> 路由至 L2。")
                return "L2-OpenManus"

        # 3. 置信度降级
        from core.config_manager import ConfigManager
        l1_threshold = ConfigManager.get("routing.l1_threshold", 0.95)
        if l1_confidence < l1_threshold:
            if vendor:
                self._record_failure(vendor)
            return "L2-OpenManus"

        return "L1-Moltbot"

    def record_feedback(self, vendor, confidence):
        """
        [Optimization 1] 记录处理反馈，实现自学习路由 (Adaptive Routing)
        原理：建立“高阶观察池”，自动识别 L1 难处理的供应商 (F3.1.4)
        """
        if not vendor: return
        
        from core.config_manager import ConfigManager
        l1_threshold = ConfigManager.get("routing.l1_threshold", 0.95)
        
        if confidence < l1_threshold:
            # 记录失败
            self.vendor_stats[vendor] = self.vendor_stats.get(vendor, {"failures": 0})
            self.vendor_stats[vendor]["failures"] += 1
            self.vendor_stats[vendor]["last_failure"] = time.time()
            
            if self.vendor_stats[vendor]["failures"] >= 3:
                # 连续 3 次低置信度，开启 48 小时强制 L2 专家路由保护
                self.forced_l2_vendors[vendor] = time.time() + 172800 
                log.warning(f"自学习路由：供应商 [{vendor}] 连续失败，进入 L2 观察名单 (48h)。")
        else:
            # 处理成功，重置失败计数
            if vendor in self.vendor_stats:
                self.vendor_stats[vendor]["failures"] = 0

    def _record_failure(self, vendor):
        stats = self.vendor_stats.get(vendor, {"failures": 0})
        stats["failures"] += 1
        stats["last_failure"] = time.time()
        self.vendor_stats[vendor] = stats
        
        if stats["failures"] >= 3:
            self.forced_l2_vendors[vendor] = time.time() + 86400
            log.warning(f"自学习路由: 供应商 [{vendor}] 处理持续低信，已加入 L2 强制路由池。")

    def reset_stats(self, vendor):
        if vendor in self.vendor_stats:
            del self.vendor_stats[vendor]
        if vendor in self.forced_l2_vendors:
            del self.forced_l2_vendors[vendor]
