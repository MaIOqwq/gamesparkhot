import pymysql, numpy as np, math

conn = pymysql.connect(host='<SERVER_IP>', port=3306, user='spark',
                       password = <DB_PASSWORD>, database='standardized_data',
                       charset='utf8mb4', connect_timeout=10, read_timeout=600)

for plat, name in [(0, 'NGA'), (1, 'B绔?)]:
    df = pd.read_sql(f"SELECT hot_raw FROM standardized_data WHERE platform={plat}", conn)
    hot_log = np.log1p(df['hot_raw'].values)
    p95 = np.percentile(hot_log, 95)
    p99 = np.percentile(hot_log, 99)
    print(f"{name} (platform={plat}): n={len(df)}, P95={p95:.4f}, P99={p99:.4f}, max={hot_log.max():.4f}")

conn.close()
