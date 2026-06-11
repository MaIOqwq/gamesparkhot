import pymysql
import math
conn = pymysql.connect(host='<SERVER_IP>', user='spark', password = <DB_PASSWORD>, database='standardized_data')
cur = conn.cursor()

for platform, name in [(1, 'bilibili'), (0, 'nga')]:
    cur.execute("""
        SELECT hot_raw, comment_count, like_count, coin_count,
               favorite_count, share_count,
               TIMESTAMPDIFF(HOUR, publish_time, created_at) AS time_diff
        FROM standardized_data WHERE platform=%s
    """, (platform,))
    rows = cur.fetchall()
    n = len(rows)
    if n == 0:
        continue

    hot_vals = sorted([r[0] for r in rows])
    cmt_vals = sorted([r[1] for r in rows])
    like_vals = sorted([r[2] for r in rows])
    time_vals = sorted([r[6] for r in rows])

    print(f"\n{'='*60}")
    print(f"{'='*60}")
    print(f"  {name.upper()}  (n={n})")
    print(f"{'='*60}")

    # --- hot_raw percentiles ---
    print(f"\n[hot_raw]")
    avg = sum(r[0] for r in rows) / n
    print(f"  avg={avg:.1f}  max={hot_vals[-1]:.1f}  min={hot_vals[0]:.1f}")
    for p, label in [(0.25,'P25'),(0.50,'P50'),(0.75,'P75'),(0.90,'P90'),(0.95,'P95'),(0.99,'P99')]:
        idx = min(int(n * p), n-1)
        print(f"  {label}={hot_vals[idx]:.1f}")

    # --- hot_raw bins ---
    bins = [0, 10, 100, 1000, 5000, 10000, 50000, 100000, 500000, 1e9]
    bin_labels = ['0-10','10-100','100-1k','1k-5k','5k-10k','10k-50k','50k-100k','100k-500k','500k+']
    print(f"  distribution:")
    for i in range(len(bins)-1):
        cnt = sum(1 for v in hot_vals if bins[i] <= v < bins[i+1])
        pct = cnt/n*100
        bar = '#' * int(pct/2)
        print(f"    {bin_labels[i]:>12s}: {cnt:>6d} ({pct:5.1f}%) {bar}")

    # --- comment_count, like_count ---
    print(f"\n[comment_count]  avg={sum(r[1] for r in rows)/n:.1f}  max={cmt_vals[-1]:.1f}")
    for p, label in [(0.50,'P50'),(0.75,'P75'),(0.90,'P90'),(0.95,'P95'),(0.99,'P99')]:
        idx = min(int(n * p), n-1)
        print(f"    {label}={cmt_vals[idx]:.1f}")

    print(f"\n[like_count]  avg={sum(r[2] for r in rows)/n:.1f}  max={like_vals[-1]:.1f}")
    for p, label in [(0.50,'P50'),(0.75,'P75'),(0.90,'P90'),(0.95,'P95'),(0.99,'P99')]:
        idx = min(int(n * p), n-1)
        print(f"    {label}={like_vals[idx]:.1f}")

    # --- time_diff distribution ---
    print(f"\n[time_diff (hours from publish to capture)]")
    print(f"  avg={sum(r[6] for r in rows)/n:.1f}h  max={time_vals[-1]:.1f}h  min={time_vals[0]:.1f}h")
    td_bins = [0, 1, 2, 6, 12, 24, 48, 72, 168, 720, 1e9]
    td_labels = ['0-1h','1-2h','2-6h','6-12h','12-24h','24-48h','48-72h','72-168h','168-720h','720h+']
    for i in range(len(td_bins)-1):
        cnt = sum(1 for v in time_vals if td_bins[i] <= v < td_bins[i+1])
        pct = cnt/n*100
        bar = '#' * int(pct/2)
        print(f"    {td_labels[i]:>12s}: {cnt:>6d} ({pct:5.1f}%) {bar}")

    # --- Approx 位 (hot_raw / time_diff) ---
    print(f"\n[Approx 位 = hot_raw / time_diff  (interactions/hour)]")
    lambda_vals = sorted([r[0] / max(r[6], 1) for r in rows])
    for p, label in [(0.50,'P50'),(0.75,'P75'),(0.90,'P90'),(0.95,'P95'),(0.99,'P99')]:
        idx = min(int(n * p), n-1)
        print(f"    {label}={lambda_vals[idx]:.1f}/h")

    # 位 buckets
    lambda_bins = [0, 0.1, 0.5, 1, 5, 10, 50, 100, 500, 1000, 1e9]
    lambda_labels = ['0-0.1','0.1-0.5','0.5-1','1-5','5-10','10-50','50-100','100-500','500-1000','1000+']
    print(f"  distribution:")
    for i in range(len(lambda_bins)-1):
        cnt = sum(1 for v in lambda_vals if lambda_bins[i] <= v < lambda_bins[i+1])
        pct = cnt/n*100
        bar = '#' * int(pct/2)
        print(f"    {lambda_labels[i]:>10s}: {cnt:>6d} ({pct:5.1f}%) {bar}")

    # --- Comment-only 位 ---
    print(f"\n[Comment 位 = comment_count / time_diff  (comments/hour)]")
    cmt_lambda = sorted([r[1] / max(r[6], 1) for r in rows])
    for p, label in [(0.50,'P50'),(0.75,'P75'),(0.90,'P90'),(0.95,'P95'),(0.99,'P99')]:
        idx = min(int(n * p), n-1)
        print(f"    {label}={cmt_lambda[idx]:.3f}/h")

    # --- hot_norm check ---
    cur.execute("SELECT hot_norm FROM standardized_data WHERE platform=%s LIMIT 5", (platform,))
    norms = [r[0] for r in cur.fetchall()]
    print(f"\n[hot_norm sample (first 5)]: {[f'{x:.3f}' for x in norms]}")

conn.close()
print("\nDone!")
