import pymysql, pandas as pd
import warnings
warnings.filterwarnings('ignore')

conn = pymysql.connect(host='<SERVER_IP>', port=3306, user='spark',
                       password = <DB_PASSWORD>, database='standardized_data', charset='utf8mb4')

# 1. crawl_queue 鐨勫叧閿瘝瑕嗙洊
craw = pd.read_sql("SELECT DISTINCT keyword, status, COUNT(*) as cnt FROM crawl_queue GROUP BY keyword", conn)
print("crawl_queue 鍏抽敭璇嶈鐩?")
for _, r in craw.iterrows():
    print(f"  {r['keyword']:<12} {r['cnt']:>5}鏉?鐘舵€佸垎甯? {r['status']}")

# 2. crawl_queue 鏃堕棿鑼冨洿
ts = pd.read_sql("SELECT MIN(first_captured) as earliest, MAX(last_visited) as latest FROM crawl_queue", conn)
print(f"\n鏃堕棿鑼冨洿: {ts['earliest'].iloc[0]} ~ {ts['latest'].iloc[0]}")

# 3. 鏈夊灏戞潯鏈?lambda 鍊?lam = pd.read_sql("SELECT COUNT(*) as total, SUM(CASE WHEN current_lambda > 0 THEN 1 ELSE 0 END) as has_lambda FROM crawl_queue", conn)
print(f"\n鏈?lambda 鍊肩殑鏉℃暟: {lam['has_lambda'].iloc[0]}/{lam['total'].iloc[0]}")

# 4. 鎸夊叧閿瘝骞冲潎 lambda
lam_kw = pd.read_sql("""
    SELECT keyword, AVG(current_lambda) as avg_lambda,
           MAX(current_lambda) as max_lambda,
           SUM(CASE WHEN current_lambda > 1 THEN 1 ELSE 0 END) as high_lambda_cnt
    FROM crawl_queue
    WHERE status = 'active'
    GROUP BY keyword ORDER BY avg_lambda DESC
""", conn)
print(f"\n娲昏穬鍐呭(鎸夊叧閿瘝)鐨勫钩鍧?lambda:")
for _, r in lam_kw.head(22).iterrows():
    print(f"  {r['keyword']:<12} 骞冲潎lambda={r['avg_lambda']:.2f} 鏈€澶ambda={r['max_lambda']:.2f} 楂樺闀挎暟={r['high_lambda_cnt']}")

# 5. 鏃堕棿瀵归綈锛氭渶杩?0澶╂瘡澶╁悇鍏抽敭璇嶆湁澶氬皯娲昏穬鐖彇鍐呭
print(f"\n鏈€杩?0澶╂瘡澶╂椿璺冪埇鍙栨暟:")
daily = pd.read_sql("""
    SELECT DATE(last_visited) as dt, keyword, COUNT(*) as cnt,
           AVG(current_lambda) as avg_lambda
    FROM crawl_queue WHERE status='active' AND last_visited >= DATE_SUB(NOW(), INTERVAL 30 DAY)
    GROUP BY dt, keyword ORDER BY dt
""", conn)
print(f"  {len(daily)} 鏉¤褰曪紝{daily['dt'].nunique()} 澶╋紝{daily['keyword'].nunique()} 涓叧閿瘝")
print(f"  鏃ュ潎娲昏穬鐖彇: {daily.groupby('dt')['cnt'].sum().mean():.0f} 鏉?)
print(f"  鏃ュ潎鏈塴ambda鏁版嵁: {daily.groupby('dt')['cnt'].sum().mean():.0f} 鏉?)

conn.close()
