#!/usr/bin/env python3
"""璇婃柇锛氭煡鐪?change_rate 鍒嗗竷锛岀‘瀹氭渶浼樺垎绫婚槇鍊?""
import configparser
import os
import logging
import pandas as pd
import numpy as np
import pymysql

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

config = configparser.ConfigParser()
config_path = 'config.ini'
if os.path.exists(config_path):
    config.read(config_path, encoding='utf-8')
else:
    config['database'] = {
        'host': '<SERVER_IP>', 'port': '3306',
        'user': 'spark', 'password': '123456', 'database': 'standardized_data',
    }

conn = pymysql.connect(
    host=config.get('database', 'host'),
    port=config.getint('database', 'port'),
    user=config.get('database', 'user'),
    password=config.get('database', 'password'),
    database=config.get('database', 'database'),
    charset='utf8mb4',
)

sql = "SELECT * FROM standardized_data WHERE publish_time >= '2023-01-01' ORDER BY keyword, publish_time"
df = pd.read_sql(sql, conn)
conn.close()
logger.info(f"鍏?{len(df)} 鏉¤褰?)

# 6灏忔椂绐楀彛鑱氬悎
df['publish_time'] = pd.to_datetime(df['publish_time'])
df['window_start'] = df['publish_time'].dt.floor('6H')

agg = df.groupby(['keyword', 'window_start']).agg({
    'hot_score': 'sum', 'like_count': 'mean', 'comment_count': 'mean',
    'view_count': 'mean',
    'id': 'count',
}).reset_index()
agg.columns = ['keyword', 'window_start', 'total_hot', 'avg_like', 'avg_comment', 'avg_view', 'count']

# 婊炲悗+鍙樺寲鐜?agg = agg.sort_values(['keyword', 'window_start'])
agg['future_total_hot'] = agg.groupby('keyword')['total_hot'].shift(-1)
agg = agg.dropna(subset=['future_total_hot'])
agg['change_rate'] = (agg['future_total_hot'] - agg['total_hot']) / (agg['total_hot'] + 1e-6)

# 缁熻 change_rate 鍒嗗竷
cr = agg['change_rate']
percentiles = [1, 5, 10, 20, 25, 30, 40, 50, 60, 70, 75, 80, 90, 95, 99]
logger.info("change_rate 鐧惧垎浣嶅垎甯?")
for p in percentiles:
    logger.info(f"  {p}%: {cr.quantile(p/100):.4f}")

logger.info(f"\n鎻忚堪缁熻:")
logger.info(f"  鍧囧€? {cr.mean():.4f}")
logger.info(f"  鏍囧噯宸? {cr.std():.4f}")
logger.info(f"  涓綅鏁? {cr.median():.4f}")
logger.info(f"  鏈€灏忓€? {cr.min():.4f}")
logger.info(f"  鏈€澶у€? {cr.max():.4f}")

# 鐪嬩笉鍚岄槇鍊间笅鐨勫垎绫诲垎甯?threshold_sets = [
    ("鍘熷闃堝€?, [(-0.5, 0), (-0.1, 1), (0.1, 2), (1.0, 3)]),
    ("瀹芥澗闃堝€?, [(-0.8, 0), (-0.2, 1), (0.2, 2), (0.8, 3)]),
    ("鍒嗕綅鏁伴槇鍊?, [(cr.quantile(0.20), 0), (cr.quantile(0.40), 1), (cr.quantile(0.60), 2), (cr.quantile(0.80), 3)]),
]

for name, thresholds in threshold_sets:
    labels = np.full(len(agg), 2)  # 榛樿骞崇ǔ
    for thresh, label in thresholds:
        if label == 0:  # 鏆磋穼 < thresh
            labels[agg['change_rate'] < thresh] = 0
        elif label == 1:  # 涓嬮檷 thresh <= change_rate < next_thresh
            next_thresh = 0.1 if name == "鍘熷闃堝€? else (0.2 if name == "瀹芥澗闃堝€? else cr.quantile(0.40))
            labels[(agg['change_rate'] >= thresh) & (agg['change_rate'] < 0)] = 1  # Hmm this doesn't work generically
    # Simpler: just show current distribution

logger.info("\n\n褰撳墠闃堝€间笅鐨勫垎甯?(鍘熷: <-0.5, -0.5~-0.1, -0.1~0.1, 0.1~1.0, >1.0):")
labels = np.full(len(agg), 2)
labels[agg['change_rate'] > 1.0] = 4
labels[(agg['change_rate'] > 0.1) & (agg['change_rate'] <= 1.0)] = 3
labels[(agg['change_rate'] < -0.1) & (agg['change_rate'] >= -0.5)] = 1
labels[agg['change_rate'] < -0.5] = 0
for label, name in [(0,'鏆磋穼'),(1,'涓嬮檷'),(2,'骞崇ǔ'),(3,'涓婂崌'),(4,'鏆存定')]:
    cnt = (labels == label).sum()
    logger.info(f"  {name}: {cnt} ({cnt/len(labels)*100:.1f}%)")

# 寤鸿鏂伴槇鍊? 浣跨敤鍒嗕綅鏁?logger.info("\n寤鸿鐨勫垎浣嶆暟闃堝€?")
# 5绛夊垎
q20, q40, q60, q80 = cr.quantile([0.20, 0.40, 0.60, 0.80])
logger.info(f"  Q20={q20:.4f}, Q40={q40:.4f}, Q60={q60:.4f}, Q80={q80:.4f}")
labels2 = np.full(len(agg), 2)
labels2[agg['change_rate'] > q80] = 4
labels2[(agg['change_rate'] > q60) & (agg['change_rate'] <= q80)] = 3
labels2[(agg['change_rate'] < q40) & (agg['change_rate'] >= q20)] = 1
labels2[agg['change_rate'] < q20] = 0
for label, name in [(0,'鏆磋穼'),(1,'涓嬮檷'),(2,'骞崇ǔ'),(3,'涓婂崌'),(4,'鏆存定')]:
    cnt = (labels2 == label).sum()
    logger.info(f"  {name}: {cnt} ({cnt/len(labels2)*100:.1f}%)")
