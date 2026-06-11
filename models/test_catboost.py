#!/usr/bin/env python3
"""CatBoost 5鍒嗙被 + 3鍒嗙被 娴嬭瘯 (keyword 浣滀负绫诲埆鐗瑰緛)"""
import configparser
import logging
import os
import warnings

import numpy as np
import pandas as pd
import pymysql
from catboost import CatBoostClassifier, Pool
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_score, TimeSeriesSplit

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

config = configparser.ConfigParser()
config_path = 'config.ini'
if os.path.exists(config_path):
    config.read(config_path, encoding='utf-8')
else:
    config['database'] = {'host': '<SERVER_IP>', 'port': '3306',
                          'user': 'spark', 'password': '123456', 'database': 'standardized_data'}

conn = pymysql.connect(host=config.get('database', 'host'), port=config.getint('database', 'port'),
                       user=config.get('database', 'user'), password=config.get('database', 'password'),
                       database=config.get('database', 'database'), charset='utf8mb4',
                       connect_timeout=10)

sql = "SELECT * FROM standardized_data WHERE publish_time >= '2023-01-01' ORDER BY keyword, publish_time"
df = pd.read_sql(sql, conn)
conn.close()
logger.info(f"鍏?{len(df)} 鏉¤褰?)

# 鐗瑰緛宸ョ▼
df['publish_time'] = pd.to_datetime(df['publish_time'])
df['window_start'] = df['publish_time'].dt.floor('6H')

agg = df.groupby(['keyword', 'window_start']).agg({
    'hot_score': ['sum', 'mean', 'max'],
    'like_count': 'sum', 'comment_count': 'sum', 'view_count': 'sum',
    'sentiment_score': 'mean', 'id': 'count',
}).reset_index()
agg.columns = ['keyword', 'window_start', 'total_hot', 'mean_hot', 'max_hot',
               'total_like', 'total_comment', 'total_view', 'avg_sentiment', 'count']
agg = agg.sort_values(['keyword', 'window_start']).reset_index(drop=True)

# 鏃剁壒寰?agg['hour'] = agg['window_start'].dt.hour
agg['day_of_week'] = agg['window_start'].dt.dayofweek
agg['is_weekend'] = (agg['day_of_week'] >= 5).astype(int)

# 婊炲悗
for i in [1, 2, 3]:
    agg[f'lag_{i}_total_hot'] = agg.groupby('keyword')['total_hot'].shift(i)
    agg[f'lag_{i}_count'] = agg.groupby('keyword')['count'].shift(i)
    agg[f'lag_{i}_total_comment'] = agg.groupby('keyword')['total_comment'].shift(i)

# 鍙樺寲鐜?agg['hot_change_rate'] = (agg['total_hot'] - agg['lag_1_total_hot']) / (agg['lag_1_total_hot'] + 1e-6)

# 瓒嬪娍鏂瑰悜
agg['trend_up_count'] = (
    ((agg['total_hot'] > agg['lag_1_total_hot']).astype(int)) +
    ((agg['lag_1_total_hot'] > agg['lag_2_total_hot']).astype(int)) +
    ((agg['lag_2_total_hot'] > agg['lag_3_total_hot']).astype(int))
)

# 鐩爣
agg['future_total_hot'] = agg.groupby('keyword')['total_hot'].shift(-1)
agg['change_rate'] = (agg['future_total_hot'] - agg['total_hot']) / (agg['total_hot'] + 1e-6)
agg = agg.dropna(subset=['future_total_hot'])

# 5鍒嗙被 (鍘熷闃堝€?
agg['label_5'] = 2
agg.loc[agg['change_rate'] > 1.0, 'label_5'] = 4
agg.loc[(agg['change_rate'] > 0.1) & (agg['change_rate'] <= 1.0), 'label_5'] = 3
agg.loc[(agg['change_rate'] < -0.1) & (agg['change_rate'] >= -0.5), 'label_5'] = 1
agg.loc[agg['change_rate'] < -0.5, 'label_5'] = 0

# 3绫绘柟鍚?(鍒嗕綅鏁板钩琛?
q30 = agg['change_rate'].quantile(0.30)
q70 = agg['change_rate'].quantile(0.70)
agg['label_3'] = 1
agg.loc[agg['change_rate'] > q70, 'label_3'] = 2
agg.loc[agg['change_rate'] < q30, 'label_3'] = 0

agg = agg.fillna(0).replace([np.inf, -np.inf], 0)

logger.info(f"鐗瑰緛瀹屾垚: {len(agg)} 鏍锋湰")
for lbl in ['label_5', 'label_3']:
    counts = agg[lbl].value_counts().sort_index()
    logger.info(f"  {lbl}: {dict(zip(counts.index, [f'{v/len(agg)*100:.1f}%' for v in counts.values]))}")

# 鐗瑰緛鍑嗗
cat_features = ['keyword']  # keyword 浣滀负绫诲埆鐗瑰緛
num_features = [
    'total_hot', 'mean_hot', 'max_hot',
    'total_like', 'total_comment', 'total_view',
    'avg_sentiment', 'count',
    'hour', 'day_of_week', 'is_weekend',
    'lag_1_total_hot', 'lag_2_total_hot', 'lag_3_total_hot',
    'lag_1_count', 'lag_2_count', 'lag_3_count',
    'lag_1_total_comment', 'lag_2_total_comment', 'lag_3_total_comment',
    'hot_change_rate', 'trend_up_count',
]

all_features = num_features + cat_features

# ===== 1. 闅忔満浜ゅ弶楠岃瘉 (CatBoost) =====
logger.info("\n========== 闅忔満 StratifiedKFold CV (CatBoost 5绫? ==========")
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
cat_cv_scores = []

for fold, (train_idx, test_idx) in enumerate(cv.split(agg[all_features], agg['label_5'])):
    train = agg.iloc[train_idx]
    test = agg.iloc[test_idx]

    train_pool = Pool(train[all_features], train['label_5'], cat_features=cat_features)
    test_pool = Pool(test[all_features], test['label_5'], cat_features=cat_features)

    model = CatBoostClassifier(
        iterations=1000, learning_rate=0.05, depth=8,
        loss_function='MultiClass', eval_metric='Accuracy',
        random_seed=42, verbose=0, early_stopping_rounds=50,
        class_weights=[0.5, 2.0, 3.0, 2.0, 0.5],  # 缁欎腑绫诲埆鏇撮珮鏉冮噸
    )
    model.fit(train_pool, eval_set=test_pool)
    pred = model.predict(test_pool)
    acc = accuracy_score(test['label_5'].values, pred)
    cat_cv_scores.append(acc)
    logger.info(f"  Fold {fold+1}: {acc:.4f}")

logger.info(f"CatBoost CV 5绫诲钩鍧囧噯纭巼: {np.mean(cat_cv_scores):.4f} (+/- {np.std(cat_cv_scores):.4f})")

# ===== 2. CatBoost 3绫绘柟鍚?=====
logger.info("\n========== CatBoost 3绫绘柟鍚?(StratifiedKFold) ==========")
cv3 = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
cat_cv3_scores = []

for fold, (train_idx, test_idx) in enumerate(cv3.split(agg[all_features], agg['label_3'])):
    train = agg.iloc[train_idx]
    test = agg.iloc[test_idx]

    train_pool = Pool(train[all_features], train['label_3'], cat_features=cat_features)
    test_pool = Pool(test[all_features], test['label_3'], cat_features=cat_features)

    model = CatBoostClassifier(
        iterations=1000, learning_rate=0.05, depth=8,
        loss_function='MultiClass', eval_metric='Accuracy',
        random_seed=42, verbose=0, early_stopping_rounds=50,
    )
    model.fit(train_pool, eval_set=test_pool)
    pred = model.predict(test_pool)
    acc = accuracy_score(test['label_3'].values, pred)
    cat_cv3_scores.append(acc)
    logger.info(f"  Fold {fold+1}: {acc:.4f}")

logger.info(f"CatBoost CV 3绫诲钩鍧囧噯纭巼: {np.mean(cat_cv3_scores):.4f} (+/- {np.std(cat_cv3_scores):.4f})")

# ===== 3. 鏃堕棿搴忓垪浜ゅ弶楠岃瘉 (CatBoost 5绫? =====
logger.info("\n========== 鏃堕棿搴忓垪 CV (CatBoost 5绫? ==========")
# 鎸夋椂闂存帓搴?agg = agg.sort_values('window_start').reset_index(drop=True)

n = len(agg)
fold_size = n // 5
ts_scores = []

for fold in range(4):  # 4涓椂闂寸偣
    train_end = (fold + 1) * fold_size
    test_end = min(train_end + fold_size, n)

    train = agg.iloc[:train_end]
    test = agg.iloc[train_end:test_end]

    if len(test) == 0 or len(train) < 100:
        continue

    train_pool = Pool(train[all_features], train['label_5'], cat_features=cat_features)
    test_pool = Pool(test[all_features], test['label_5'], cat_features=cat_features)

    model = CatBoostClassifier(
        iterations=500, learning_rate=0.05, depth=8,
        loss_function='MultiClass', eval_metric='Accuracy',
        random_seed=42, verbose=0, early_stopping_rounds=50,
        class_weights=[0.5, 2.0, 3.0, 2.0, 0.5],
    )
    model.fit(train_pool)
    pred = model.predict(test_pool)
    acc = accuracy_score(test['label_5'].values, pred)
    ts_scores.append(acc)
    logger.info(f"  鏃堕棿Fold {fold+1}: train<={train['window_start'].max()}, acc={acc:.4f}")

if ts_scores:
    logger.info(f"鏃堕棿搴忓垪CV骞冲潎鍑嗙‘鐜? {np.mean(ts_scores):.4f}")

# ===== 4. XGBoost 闅忔満浜ゅ弶楠岃瘉 (瀵规瘮) =====
from xgboost import XGBClassifier
logger.info("\n========== XGBoost 闅忔満 CV (5绫? ==========")

from sklearn.preprocessing import LabelEncoder
le = LabelEncoder()
agg['keyword_enc'] = le.fit_transform(agg['keyword'])
xgb_features = [c for c in all_features if c != 'keyword'] + ['keyword_enc']

xgb_cv_scores = []
for fold, (train_idx, test_idx) in enumerate(cv.split(agg[xgb_features], agg['label_5'])):
    train = agg.iloc[train_idx]
    test = agg.iloc[test_idx]

    model = XGBClassifier(
        objective='multi:softprob', num_class=5, eval_metric='mlogloss',
        max_depth=8, learning_rate=0.05, n_estimators=1000,
        subsample=0.8, colsample_bytree=0.8,
        reg_lambda=3.0, reg_alpha=1.0,
        random_state=42, early_stopping_rounds=50,
    )
    model.fit(train[xgb_features], train['label_5'],
              eval_set=[(test[xgb_features], test['label_5'])], verbose=0)
    pred = model.predict(test[xgb_features])
    acc = accuracy_score(test['label_5'].values, pred)
    xgb_cv_scores.append(acc)
    logger.info(f"  Fold {fold+1}: {acc:.4f}")

logger.info(f"XGBoost CV 5绫诲钩鍧囧噯纭巼: {np.mean(xgb_cv_scores):.4f} (+/- {np.std(xgb_cv_scores):.4f})")

# ===== 鎬荤粨 =====
logger.info("\n" + "=" * 50)
logger.info("鏈€缁堝姣?")
logger.info(f"CatBoost 5绫?(闅忔満CV): {np.mean(cat_cv_scores)*100:.2f}%")
logger.info(f"CatBoost 3绫?(闅忔満CV): {np.mean(cat_cv3_scores)*100:.2f}%")
logger.info(f"XGBoost 5绫?(闅忔満CV): {np.mean(xgb_cv_scores)*100:.2f}%")
logger.info(f"CatBoost 5绫?(鏃堕棿CV): {np.mean(ts_scores)*100:.2f}%" if ts_scores else "鏃堕棿CV: N/A")
