from core.db_helper import DBHelper
import os
import sys

def test_connection():
    print("正在测试 PostgreSQL 连接和初始化...")
    try:
        # 显式加载环境变量，确保配置正确
        from dotenv import load_dotenv
        load_dotenv()
        
        db = DBHelper()
        print("数据库连接成功！")
        
        print("测试插入系统事件...")
        db.log_system_event("TEST_EVENT", "DB_MIGRATOR", "Migration test event")
        
        print("测试心跳更新...")
        db.update_heartbeat("DB_MIGRATOR", status="TESTING")
        
        print("测试健康检查...")
        is_healthy = db.check_health("DB_MIGRATOR")
        print(f"健康检查结果: {is_healthy}")
        
        if is_healthy:
            print("所有测试通过！")
            return True
        else:
            print("健康检查失败。")
            return False
            
    except Exception as e:
        print(f"测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # 将 src 添加到 python path
    sys.path.append(os.path.join(os.getcwd(), "src"))
    success = test_connection()
    sys.exit(0 if success else 1)
