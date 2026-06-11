import pymysql
from collections import defaultdict
import json

conn = pymysql.connect(host='<SERVER_IP>', user='spark', password = <DB_PASSWORD>, database='standardized_data')
cur = conn.cursor()

# 鏈€杩?0澶?vs 鍓?0澶?鐨勭獥鍙ｅ彉鍖?# 鍏堟妸鍙戝竷鍦ㄦ渶杩?60 澶╁唴鐨勬暟鎹紝鎸夊叧閿瘝姹囨€伙紝鍒嗗墠30澶╁拰鍚?0澶?cur.execute("""
    SELECT keyword,
        SUM(CASE WHEN publish_time >= DATE_SUB(NOW(), INTERVAL 30 DAY) THEN hot_raw ELSE 0 END) as hot_recent,
        SUM(CASE WHEN publish_time >= DATE_SUB(NOW(), INTERVAL 30 DAY) THEN 1 ELSE 0 END) as cnt_recent,
        SUM(CASE WHEN publish_time >= DATE_SUB(NOW(), INTERVAL 60 DAY)
                  AND publish_time < DATE_SUB(NOW(), INTERVAL 30 DAY) THEN hot_raw ELSE 0 END) as hot_prev,
        SUM(CASE WHEN publish_time >= DATE_SUB(NOW(), INTERVAL 60 DAY)
                  AND publish_time < DATE_SUB(NOW(), INTERVAL 30 DAY) THEN 1 ELSE 0 END) as cnt_prev,
        SUM(CASE WHEN publish_time >= DATE_SUB(NOW(), INTERVAL 1 DAY) THEN 1 ELSE 0 END) as cnt_24h
    FROM standardized_data
    WHERE publish_time >= DATE_SUB(NOW(), INTERVAL 60 DAY)
    GROUP BY keyword
    HAVING hot_recent > 0 AND hot_prev > 0
    ORDER BY hot_recent DESC
""")
rows = cur.fetchall()

alerts = []
for r in rows:
    kw = r[0]
    hot_recent = float(r[1])
    cnt_recent = int(r[2])
    hot_prev = float(r[3])
    cnt_prev = int(r[4])
    cnt_24h = int(r[5])

    # 鍙樺寲鐜?    change_pct = round((hot_recent - hot_prev) / hot_prev * 100, 1)

    # 绠€鍗曢槇鍊煎垎绫伙紙鍚庣画鏇挎崲涓烘ā鍨嬮娴?位闃堝€硷級
    if change_pct > 100:
        level = "danger"
        tag = f"鏆存定 +{change_pct}%"
    elif change_pct > 30:
        level = "warning"
        tag = f"涓婂崌 +{change_pct}%"
    elif change_pct > -10:
        level = "info"
        tag = f"骞崇ǔ {change_pct:+.1f}%"
    elif change_pct > -40:
        level = "normal"
        tag = f"涓嬮檷 {change_pct:+.1f}%"
    else:
        level = "normal"
        tag = f"鏆磋穼 {change_pct:+.1f}%"

    alerts.append({
        "keyword": kw,
        "level": level,
        "tag": tag,
        "hot_recent": int(hot_recent),
        "cnt_recent": cnt_recent,
        "cnt_24h": cnt_24h,
        "change_pct": change_pct
    })

# 鎸夊彉鍖栫巼缁濆鍊兼帓搴?alerts.sort(key=lambda x: abs(x["change_pct"]), reverse=True)

# 缁熻
surging = sum(1 for a in alerts if a["change_pct"] > 100)
rising = sum(1 for a in alerts if 30 < a["change_pct"] <= 100)
stable = sum(1 for a in alerts if -10 < a["change_pct"] <= 30)

output = {
    "updated_at": "瀹炴椂",
    "stats": {
        "surging": surging,
        "rising": rising,
        "stable": stable
    },
    "alerts": alerts[:20]
}

with open("e:\\cc-connect\\warning_data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"鍏?{len(alerts)} 涓叧閿瘝鏈夋暟鎹?)
print(f"鏆存定: {surging}, 涓婂崌: {rising}, 骞崇ǔ/鍏朵粬: {stable}")
print(f"TOP 10 棰勮:")
for a in alerts[:10]:
    print(f"  [{a['level']}] {a['keyword']}: {a['tag']}  (杩?0d鐑害={a['hot_recent']}, 杩?4h={a['cnt_24h']}鏉?")

conn.close()
