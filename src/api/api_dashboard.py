import json
from datetime import datetime
from core.db_helper import DBHelper

def render_dashboard(stats, roi, trend, archived_count, global_total, recent_tx, svc_stats):
    def format_date(d):
        if hasattr(d, 'day'): return f"{d.day:02d}"
        return str(d)[-2:]
    
    total_active = sum(s['count'] for s in stats if s['status'] != 'REJECTED')
    audit_passed = sum(s['count'] for s in stats if s['status'] in ('AUDITED', 'POSTED', 'COMPLETED'))
    pass_rate = round((audit_passed / total_active * 100), 1) if total_active > 0 else 100.0
    pending_count = next((s['count'] for s in stats if s['status'] == 'PENDING'), 0)
    
    trend_html = " | ".join([f"{format_date(t['report_date'])}日: {t['human_hours_saved']:.1f}h" for t in trend])
    
    roi_html = f"""
    <div class="card" style="border-left: 5px solid #2196F3;">
        <h2 style="margin-top: 0;">💰 效益快报 (ROI)</h2>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
            <div><p>累计节省人工: <b>{roi.get('human_hours_saved', 0)}</b> 小时</p><p>全量业务金额: <b>￥{global_total:,.2f}</b></p><p>最近一小时入账: <b>{recent_tx}</b> 笔</p></div>
            <div><p>系统处理通过率: <b style="color: {'#4CAF50' if pass_rate > 90 else '#FF9800'};">{pass_rate}%</b></p><p>历史归档总数: <b>{archived_count}</b> 笔</p><p>待处理积压: <b style="color: {'#f44336' if pending_count > 10 else '#2196F3'};">{pending_count}</b> 笔</p></div>
        </div>
        <p style="font-size: 0.9em; color: #555; margin-top: 15px; border-top: 1px solid #eee; padding-top: 10px;"><b>最近 7 天趋势:</b> {trend_html}</p>
    </div>
    """
    rows_html = "".join([f"<tr><td>{s['display_name']}</td><td>{s['count']}</td><td>￥{s['total_amount'] or 0:,.2f}</td></tr>" for s in stats])
    
    svc_rows = ""
    for svc in svc_stats:
        m = json.loads(svc["metrics"]) if svc["metrics"] else {}
        cpu = f"{m.get('cpu_percent', 'N/A'):.1f}%" if isinstance(m.get('cpu_percent'), (int, float)) else "N/A"
        mem = f"{m.get('memory_mb', 'N/A'):.1f}MB" if isinstance(m.get('memory_mb'), (int, float)) else "N/A"
        svc_rows += f"<tr><td>{svc['service_name']}</td><td>{svc['status']}</td><td>{cpu} / {mem}</td><td>{svc['last_heartbeat']}</td></tr>"

    return f"""
    <html><head><title>LedgerAlpha Dashboard</title><style>
        body {{ font-family: sans-serif; padding: 20px; max-width: 900px; margin: auto; background: #f9f9f9; }}
        .card {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f2f2f2; }}
    </style></head><body>
        <h1>🐶 LedgerAlpha 运行看板</h1>{roi_html}
        <div class="card"><h2>📊 账务状态分布</h2><table><tr><th>业务状态</th><th>单据笔数</th><th>合计金额</th></tr>{rows_html}</table></div>
        <div class="card"><h2>串 核心服务心跳</h2><table><tr><th>服务名称</th><th>运行状态</th><th>资源占用 (CPU/MEM)</th><th>最后心跳</th></tr>{svc_rows}</table></div>
        <p style="text-align: center; color: #999;">系统版本: v1.5.0-perfect | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </body></html>
    """
