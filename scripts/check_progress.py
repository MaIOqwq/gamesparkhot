"""Check what's been implemented vs what's still needed from 绯荤粺鏀硅繘鏂规"""
import pymysql

conn = pymysql.connect(
    host='<SERVER_IP>', user='spark', password = <DB_PASSWORD>,
    database='standardized_data', port=3306
)
cur = conn.cursor()

print("=== 鏁版嵁搴撹〃鐘舵€?===")
cur.execute('SHOW TABLES')
for t in cur.fetchall():
    cur.execute(f'SELECT COUNT(*) FROM {t[0]}')
    print(f"  {t[0]}: {cur.fetchone()[0]} rows")

# Check columns in standardized_data
cur.execute("DESCRIBE standardized_data")
cols = {c[0]: c[1] for c in cur.fetchall()}
print(f"\n=== standardized_data 鍒? {len(cols)} ===")
print(f"  鍚?hot_raw: {'hot_raw' in cols}")
print(f"  鍚?hot_norm: {'hot_norm' in cols}")
print(f"  鍚?hot_score: {'hot_score' in cols}")
print(f"  鍚?sentiment_score: {'sentiment_score' in cols}")

# Check unique platforms
cur.execute("SELECT DISTINCT platform FROM standardized_data")
print(f"\n骞冲彴: {[r[0] for r in cur.fetchall()]}")

# Check data freshness
cur.execute("SELECT MIN(created_at), MAX(created_at) FROM standardized_data")
r = cur.fetchone()
print(f"\n鏁版嵁鏃堕棿鑼冨洿: {r[0]} ~ {r[1]}")
cur.execute("SELECT TIMESTAMPDIFF(MINUTE, %s, NOW())", (r[1],))
minutes_ago = cur.fetchone()[0]
print(f"鏈€鏂版暟鎹窛鐜板湪: {minutes_ago:.1f} 鍒嗛挓")

cur.close()
conn.close()

print("\n=== 鏀硅繘鏂规瀹炴柦妫€鏌ユ竻鍗?===")
print("""
1锔忊儯  鍋滄 Spark Master/Worker   - 鉂?闇€瑕丼SH
2锔忊儯  NGA鐖櫕 cloudscraper         - 鉂?寰呮鏌?3锔忊儯  B绔欑埇铏幓鎾斁閲忛檺鍒?2h绐楀彛   - 鉂?寰呮鏌?4锔忊儯  鏂板缓 content_metrics 琛?      - 鉂?涓嶅瓨鍦?5锔忊儯  鏂板缓 crawl_queue 琛?          - 鉂?涓嶅瓨鍦?6锔忊儯  Spark 鍐欏叆鏀逛负 UPSERT         - 鉂?寰呬慨鏀?7锔忊儯  鍥炶鑴氭湰                      - 鉂?鏈紪鍐?8锔忊儯  棰勬祴妯″瀷 XGBoost              - 鉁?宸茶缁?9锔忊儯  棰勬祴鎺ュ叆鍓嶇 TrendChart       - 鉁?宸插畬鎴?馃敓  棰勮闈㈡澘 + 鎯呮劅鏃堕棿绾?        - 鉁?宸插畬鎴?""")
