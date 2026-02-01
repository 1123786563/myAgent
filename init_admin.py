#!/usr/bin/env python3
"""
初始化管理员用户脚本
Initialize Admin User Script

用户名: admin@admin
密码: admin
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from core.db_helper import DBHelper
from core.auth_models import User, Organization, Role
from auth.services.password_service import get_password_service
from auth.permissions import RoleType
from sqlalchemy.orm import Session


def init_admin_user():
    """初始化管理员用户"""
    print("=" * 60)
    print("开始初始化管理员用户...")
    print("=" * 60)

    db = DBHelper()
    password_service = get_password_service()

    org_name = ""
    admin_role_display = ""

    with db.transaction() as session:
        # 检查用户是否已存在
        existing_user = session.query(User).filter_by(email="admin@admin").first()
        if existing_user:
            print(f"\n用户 admin@admin 已存在 (ID: {existing_user.id})")
            
            # 检查是否是管理员
            roles = [role.name for role in existing_user.roles]
            print(f"当前角色: {', '.join(roles) if roles else '无'}")
            
            response = input("\n是否更新密码为 'admin'? (y/n): ")
            if response.lower() == 'y':
                password_hash = password_service.hash_password("admin")
                existing_user.password_hash = password_hash
                existing_user.is_active = True
                session.flush()
                print("密码已更新为 'admin'")
            else:
                print("保持现有密码不变")
            
            # 确保有管理员角色
            admin_role = session.query(Role).filter_by(
                name=RoleType.ADMIN.value,
                organization_id=existing_user.organization_id
            ).first()
            
            if admin_role and admin_role not in existing_user.roles:
                existing_user.roles.append(admin_role)
                session.flush()
                print(f"已添加 {RoleType.ADMIN.value} 角色")
            
            print("\n管理员用户初始化完成!")
            print(f"用户名: admin@admin")
            print(f"密码: admin")
            return

        # 获取或创建默认组织
        org = session.query(Organization).filter_by(slug="default").first()
        if not org:
            org = Organization(
                name="默认组织",
                slug="default",
                is_active=True
            )
            session.add(org)
            session.flush()
            print(f"\n创建默认组织: {org.name} (ID: {org.id})")
        else:
            print(f"\n使用现有组织: {org.name} (ID: {org.id})")
        
        org_name = org.name

        # 创建管理员用户
        password_hash = password_service.hash_password("admin")
        user = User(
            email="admin@admin",
            password_hash=password_hash,
            full_name="系统管理员",
            organization_id=org.id,
            is_active=True,
            is_verified=True
        )
        session.add(user)
        session.flush()
        print(f"创建用户: {user.email} (ID: {user.id})")

        # 创建或获取管理员角色
        admin_role = session.query(Role).filter_by(
            name=RoleType.ADMIN.value,
            organization_id=org.id
        ).first()

        if not admin_role:
            admin_role = Role(
                name=RoleType.ADMIN.value,
                display_name="管理员",
                description="组织管理员，拥有完整的管理权限",
                organization_id=org.id,
                is_system_role=True,
                priority=80
            )
            session.add(admin_role)
            session.flush()
            print(f"创建角色: {admin_role.name}")
        else:
            print(f"使用现有角色: {admin_role.name}")
        
        admin_role_display = admin_role.display_name

        # 分配管理员角色
        user.roles.append(admin_role)
        session.flush()
        print(f"分配角色: {admin_role.name}")

    print("\n" + "=" * 60)
    print("管理员用户初始化完成!")
    print("=" * 60)
    print(f"用户名: admin@admin")
    print(f"密码: admin")
    print(f"组织: {org_name}")
    print(f"角色: {admin_role_display}")
    print("=" * 60)


if __name__ == "__main__":
    try:
        init_admin_user()
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
