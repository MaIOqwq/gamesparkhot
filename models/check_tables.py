import pymysql
conn = pymysql.connect(host='<SERVER_IP>', port=3306, user='spark',
                       password = <DB_PASSWORD>, database='standardized_data', charset='utf8mb4')
cursor = conn.cursor()
cursor.execute("SELECT status, COUNT(*) FROM crawl_queue GROUP BY status")
print("crawl_queue 鐘舵€佸垎甯?")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]}")
print()
cursor.execute("SELECT * FROM crawl_queue ORDER BY current_lambda DESC LIMIT 10")
print("鎸?current_lambda 闄嶅簭 Top 10:")
for row in cursor.fetchall():
    print(f"  id={row[0]} kw={row[4]} platform={row[2]} lambda={row[8]:.2f} revisit={row[9]} status={row[14]}")
print()
cursor.execute("SELECT * FROM crawl_queue LIMIT 5")
print("闅忔満 5 鏉?")
for row in cursor.fetchall():
    print(f"  id={row[0]} kw={row[4]} platform={row[2]} lambda={row[8]:.2f} revisit={row[9]} hot_raw={row[12]} status={row[14]}")
cursor.close()
conn.close()
