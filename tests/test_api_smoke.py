import requests
import time
import os
from decimal import Decimal

# 配置
API_BASE = "http://localhost:8000"
ADMIN_KEY = "ledger-secret-2025"
HEADERS = {"X-API-Key": ADMIN_KEY}

def test_health():
    print("Testing /health...")
    try:
        resp = requests.get(f"{API_BASE}/health")
        print(f"Health: {resp.status_code}, {resp.json()}")
    except Exception as e:
        print(f"Health check failed: {e}")

def test_stats():
    print("\nTesting /stats...")
    try:
        resp = requests.get(f"{API_BASE}/stats", headers=HEADERS)
        print(f"Stats: {resp.status_code}, {resp.json()}")
    except Exception as e:
        print(f"Stats check failed: {e}")

def test_dashboard():
    print("\nTesting /dashboard...")
    try:
        resp = requests.get(f"{API_BASE}/dashboard", headers=HEADERS)
        print(f"Dashboard: {resp.status_code}, length: {len(resp.text)}")
    except Exception as e:
        print(f"Dashboard check failed: {e}")

if __name__ == "__main__":
    # 等待服务启动
    print("Waiting for API server to start...")
    time.sleep(5)
    test_health()
    test_stats()
    test_dashboard()
