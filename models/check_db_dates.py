import pymysql, pandas as pd
conn = pymysql.connect(host='<SERVER_IP>', port=3306, user='spark', password = <DB_PASSWORD>, database='standardized_data', charset='utf8mb4')
df = pd.read_sql("SELECT YEAR(publish_time) as yr, COUNT(*) as cnt FROM standardized_data GROUP BY yr ORDER BY yr", conn)
conn.close()
print(f"{'骞翠唤':>6} {'鏉℃暟':>8}")
print("-"*16)
for _, r in df.iterrows():
    yr = int(r['yr'])
    cnt = int(r['cnt'])
    bar = '#' * (cnt // 100)
    print(f"{yr:>6} {cnt:>8} {bar}")
