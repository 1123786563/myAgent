from sqlalchemy import event, inspect
from sqlalchemy.orm import Session, object_mapper
from sqlalchemy.orm.attributes import get_history

from core.db_models import Base
from core.auth_models import AuditLog
from infra.trace_context import TraceContext
from infra.logger import get_logger
import json
import datetime

log = get_logger("AuditListener")

def _get_serialization_safe_value(val):
    """将值转换为 JSON 安全的格式"""
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.isoformat()
    if hasattr(val, "to_dict"):
        return val.to_dict()
    # 简单的对象转字符串，复杂对象可能需要更细致的处理
    if val is not None and not isinstance(val, (int, float, str, bool, list, dict, type(None))):
        return str(val)
    return val

def create_audit_record(connection, target, action):
    """创建审计记录并直接插入数据库"""
    # 1. 跳过审计日志表本身，防止递归
    if isinstance(target, AuditLog):
        return

    # 2. 获取上下文信息
    # 这些信息需要由 Middleware 或业务逻辑写入 TraceContext
    user_id = TraceContext.get_attribute("user_id")
    organization_id = TraceContext.get_attribute("organization_id") or getattr(target, "organization_id", None)
    trace_id = TraceContext.get_trace_id()
    ip_address = TraceContext.get_attribute("ip_address")
    user_agent = TraceContext.get_attribute("user_agent")

    # 如果是系统内部操作且没有上下文，记录为 System
    if not user_id and not trace_id:
        # 可选：决定是否记录完全无上下文的变更。通常建议记录，标记为 System。
        # return
        pass

    # 3. 提取变更数据
    mapper = object_mapper(target)
    resource_type = mapper.class_.__name__
    # 尝试获取主键 ID
    primary_keys = [getattr(target, col.name) for col in mapper.primary_key]
    resource_id = str(primary_keys[0]) if primary_keys else "unknown"

    changes = {"old": {}, "new": {}}

    if action == 'DELETE':
        # 记录所有字段作为 old_values
        for prop in mapper.iterate_properties:
            if hasattr(prop, 'columns'):
                key = prop.key
                val = getattr(target, key)
                changes["old"][key] = _get_serialization_safe_value(val)
    else:
        # INSERT 或 UPDATE
        # 遍历所有属性检查变更
        for prop in mapper.iterate_properties:
            if not hasattr(prop, 'columns'): continue # 跳过关系属性
            key = prop.key

            # 获取属性历史
            history = get_history(target, key)

            if action == 'INSERT':
                # 新增时，added 有值，deleted 为空
                if history.has_changes():
                    val = history.added[0] if history.added else getattr(target, key)
                    changes["new"][key] = _get_serialization_safe_value(val)
            elif action == 'UPDATE':
                # 更新时，比较变更
                if history.has_changes():
                    old_val = history.deleted[0] if history.deleted else None
                    new_val = history.added[0] if history.added else getattr(target, key)

                    # 只有值真正改变才记录
                    if old_val != new_val:
                        changes["old"][key] = _get_serialization_safe_value(old_val)
                        changes["new"][key] = _get_serialization_safe_value(new_val)

    # 如果没有实际变更（Update 但值未变），跳过
    if action == 'UPDATE' and not changes["old"] and not changes["new"]:
        return

    # 4. 构建插入语句
    # 直接使用 connection.execute 插入，避免 Session 混乱
    try:
        connection.execute(
            AuditLog.__table__.insert(),
            {
                "user_id": user_id,
                "organization_id": organization_id,
                "action": f"{resource_type}.{action}",
                "resource_type": resource_type,
                "resource_id": resource_id,
                "old_values": changes["old"], # SQLAlchemy 会自动处理 JSON 序列化
                "new_values": changes["new"],
                "ip_address": ip_address,
                "user_agent": user_agent,
                "trace_id": trace_id,
                "created_at": datetime.datetime.now(),
                "status": "SUCCESS"
            }
        )
    except Exception as e:
        log.error(f"Failed to write audit log for {resource_type}:{resource_id}: {e}")

# 定义事件处理函数
def after_insert(mapper, connection, target):
    create_audit_record(connection, target, 'INSERT')

def after_update(mapper, connection, target):
    create_audit_record(connection, target, 'UPDATE')

def after_delete(mapper, connection, target):
    create_audit_record(connection, target, 'DELETE')

def setup_audit_listeners(base_model=Base):
    """
    启动审计监听
    在应用启动时调用: setup_audit_listeners(Base)
    """
    # 为所有继承自 Base 的模型注册监听器
    # 注意：这需要在模型加载后调用，或者直接监听 Base (SQLAlchemy 支持)

    event.listen(base_model, 'after_insert', after_insert, propagate=True)
    event.listen(base_model, 'after_update', after_update, propagate=True)
    event.listen(base_model, 'after_delete', after_delete, propagate=True)

    log.info("SQLAlchemy Audit Listeners registered.")
