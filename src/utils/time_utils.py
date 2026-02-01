from datetime import datetime, timezone

def get_now_utc():
    """
    统一获取 UTC 时间，防止不同环境下时钟偏移问题
    """
    return datetime.now(timezone.utc)

def format_timestamp(dt=None):
    if dt is None:
        dt = get_now_utc()
    return dt.strftime("%Y-%m-%d %H:%M:%S %Z")
