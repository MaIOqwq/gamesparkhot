"""
鍥炲綊棰勬祴 hot_raw v4 鈥?鐩存帴棰勬祴涓嬩竴鍛ㄦ湡鐨?hot_raw 鎬诲€?"""
import json, warnings
import numpy as np
import pandas as pd
import pymysql
from datetime import datetime
from sklearn.preprocessing import RobustScaler, LabelEncoder
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor
import lightgbm as lgb

warnings.filterwarnings('ignore')
print(f"[{datetime.now():%H:%M:%S}] 杩炴帴鏁版嵁搴?..")
conn = pymysql.connect(host='<SERVER_IP>', port=3306, user='spark',
                       password = <DB_PASSWORD>, database='standardized_data',
                       charset='utf8mb4', connect_timeout=10, read_timeout=600)
df = pd.read_sql("SELECT * FROM standardized_data WHERE publish_time >= '2023-01-01' ORDER BY keyword, publish_time", conn)
conn.close()
print(f"鍏?{len(df)} 鏉¤褰?)

# ========= 鐗瑰緛宸ョ▼ =========
print(f"[{datetime.now():%H:%M:%S}] 鐗瑰緛宸ョ▼...")
df['publish_time'] = pd.to_datetime(df['publish_time'])
df['window_start'] = df['publish_time'].dt.floor('6H')

agg = df.groupby(['keyword', 'window_start']).agg(
    total_hot=('hot_raw', 'sum'),
    total_like=('like_count', 'sum'),
    avg_like=('like_count', 'mean'),
    total_comment=('comment_count', 'sum'),
    avg_comment=('comment_count', 'mean'),
    total_view=('view_count', 'sum'),
    avg_view=('view_count', 'mean'),
    total_coin=('coin_count', 'sum'),
    total_favorite=('favorite_count', 'sum'),
    total_share=('share_count', 'sum'),
    avg_sentiment=('sentiment_score', 'mean'),
    count=('id', 'count'),
).reset_index()

agg = agg.sort_values(['keyword', 'window_start']).reset_index(drop=True)

# 缁勫悎鐗瑰緛
agg['total_interact'] = agg['total_like'] + agg['total_comment'] + agg['total_share']
agg['log_total_hot'] = np.log1p(agg['total_hot'])
agg['log_count'] = np.log1p(agg['count'])
agg['hot_per_post'] = agg['total_hot'] / (agg['count'] + 1)
agg['comment_rate'] = agg['total_comment'] / (agg['total_interact'] + 1)

# 鏃堕棿鐗瑰緛
agg['hour'] = agg['window_start'].dt.hour
agg['day_of_week'] = agg['window_start'].dt.dayofweek
agg['is_weekend'] = (agg['day_of_week'] >= 5).astype(int)

# 婊炲悗鐗瑰緛
for feat in ['total_hot', 'count', 'total_comment', 'avg_sentiment', 'total_like']:
    for i in [1, 2, 3, 6, 12]:
        agg[f'lag_{i}_{feat}'] = agg.groupby('keyword')[feat].shift(i)

# 鍙樺寲鐜?for t in [1, 3, 6]:
    agg[f'pct_{t}'] = (agg['total_hot'] - agg[f'lag_{t}_total_hot']) / (agg[f'lag_{t}_total_hot'] + 1e-6)

# 婊氬姩缁熻
for feat in ['total_hot', 'count', 'avg_sentiment']:
    for w in [3, 6, 12]:
        r = agg.groupby('keyword')[feat].rolling(w)
        agg[f'rm_{w}_{feat}'] = r.mean().reset_index(level=0, drop=True)
        agg[f'rmax_{w}_{feat}'] = r.max().reset_index(level=0, drop=True)
        agg[f'rstd_{w}_{feat}'] = r.std().reset_index(level=0, drop=True)

agg['hot_vs_rm3'] = agg['total_hot'] / (agg['rm_3_total_hot'] + 1e-6)
agg['hot_vs_rm6'] = agg['total_hot'] / (agg['rm_6_total_hot'] + 1e-6)
agg['momentum_3'] = agg['pct_1'] - agg['pct_3']
agg['momentum_6'] = agg['pct_1'] - agg['pct_6']

# ========= Target (log 鍙樻崲) =========
# 棰勬祴涓嬩竴绐楀彛鐨?log(total_hot + 1)锛岄伩鍏嶆暟鍊艰寖鍥磋繃澶?agg['target_raw'] = agg.groupby('keyword')['total_hot'].shift(-1)
agg['target'] = np.log1p(agg['target_raw'])
agg = agg.dropna(subset=['target'])
print(f"Target 鎻忚堪: min={agg['target'].min():.0f}, max={agg['target'].max():.0f}, "
      f"mean={agg['target'].mean():.0f}, median={agg['target'].median():.0f}")

# keyword 缂栫爜
ke = LabelEncoder()
agg['kw'] = ke.fit_transform(agg['keyword'])
kw_map = dict(zip(ke.classes_, ke.transform(ke.classes_)))

# 鐗瑰緛鍒?exclude = {'keyword', 'window_start', 'target', 'target_raw'}
all_feats = [c for c in agg.columns if c not in exclude and agg[c].dtype in ('float64', 'int64', 'float32', 'int32')]
agg = agg.fillna(0).replace([np.inf, -np.inf], 0)
print(f"鐗瑰緛鏁? {len(all_feats)}")

# ========= 鏃堕棿鍒掑垎 =========
train_df = agg[agg['window_start'] < '2026-01-01']
val_df = train_df[train_df['window_start'] >= '2025-10-01']  # 浠庤缁冮泦灏鹃儴鍒掗獙璇?train_df = train_df[train_df['window_start'] < '2025-10-01']
test_df = agg[agg['window_start'] >= '2026-01-01']
print(f"璁粌={len(train_df)} (2023-01 ~ 2025-09), 楠岃瘉={len(val_df)} (2025-10 ~ 2025-12), 娴嬭瘯={len(test_df)} (2026+)")

X_train, y_train = train_df[all_feats], train_df['target']
X_val, y_val = val_df[all_feats], val_df['target']
X_test, y_test = test_df[all_feats], test_df['target']

# ========= Scaling =========
scaler = RobustScaler()
X_train_s = pd.DataFrame(scaler.fit_transform(X_train), columns=all_feats, index=X_train.index)
X_val_s = pd.DataFrame(scaler.transform(X_val), columns=all_feats, index=X_val.index)
X_test_s = pd.DataFrame(scaler.transform(X_test), columns=all_feats, index=X_test.index)

# ========= 妯″瀷璁粌 =========
print(f"\n[{datetime.now():%H:%M:%S}] 璁粌 XGBRegressor...")
xgb = XGBRegressor(
    n_estimators=3000, max_depth=6, learning_rate=0.02,
    subsample=0.6, colsample_bytree=0.6,
    reg_lambda=10, reg_alpha=5, min_child_weight=7,
    random_state=42, tree_method='hist', early_stopping_rounds=100,
)
xgb.fit(X_train_s, y_train, eval_set=[(X_val_s, y_val)], verbose=False)

# ========= 璇勪及 =========
def evaluate(y_true_log, y_pred_log, desc=""):
    y_true = np.expm1(y_true_log)
    y_pred = np.expm1(y_pred_log)
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2 = r2_score(y_true_log, y_pred_log)
    # 鍙 y_true > 0 绠?MAPE
    mask = y_true > 0
    mape = np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100 if mask.sum() > 0 else 0
    med_ae = np.median(np.abs(y_true - y_pred))
    print(f"  {desc}: MAE={mae:.0f}, RMSE={rmse:.0f}, MedAE={med_ae:.0f}, R2(log)={r2:.4f}, MAPE={mape:.1f}%")
    return mae, med_ae, r2, mape

print(f"\n[{datetime.now():%H:%M:%S}] 璇勪及...")
y_pred_train = xgb.predict(X_train_s)
evaluate(y_train, y_pred_train, "璁粌闆?)
y_pred_val = xgb.predict(X_val_s)
evaluate(y_val, y_pred_val, "楠岃瘉闆?)
y_pred_test = xgb.predict(X_test_s)
test_mae, test_medae, test_r2, test_mape = evaluate(y_test, y_pred_test, "娴嬭瘯闆?)

# 棰濆鎸囨爣锛氬師濮嬪昂搴﹁宸?< 30% 鐨勬瘮渚?y_test_raw = np.expm1(y_test)
y_pred_test_raw = np.expm1(y_pred_test)
mask_raw = y_test_raw > 0
if mask_raw.sum() > 0:
    relative_error = np.abs((y_test_raw[mask_raw] - y_pred_test_raw[mask_raw]) / y_test_raw[mask_raw])
    within_30pct = np.mean(relative_error < 0.30) * 100
    within_50pct = np.mean(relative_error < 0.50) * 100
else:
    within_30pct = within_50pct = 0
print(f"  璇樊<30%: {within_30pct:.1f}%, 璇樊<50%: {within_50pct:.1f}%")

# 鐗瑰緛閲嶈鎬?importances = sorted(zip(all_feats, xgb.feature_importances_), key=lambda x: -x[1])
print(f"\nTop 10 鐗瑰緛:")
for name, imp in importances[:10]:
    print(f"  {name}: {imp:.4f}")

# ========= 淇濆瓨 =========
xgb.save_model('trend_regression_model.json')
meta = {
    'model_type': 'xgboost_regression',
    'feature_columns': all_feats,
    'keyword_encoding': {str(k): int(v) for k, v in kw_map.items()},
    'scaler_center': scaler.center_.tolist() if hasattr(scaler, 'center_') else [],
    'scaler_scale': scaler.scale_.tolist() if hasattr(scaler, 'scale_') else [],
    'test_mae': float(test_mae),
    'test_medae': float(test_medae),
    'test_r2': float(test_r2),
    'test_mape': float(test_mape),
    'within_30pct': float(within_30pct),
    'within_50pct': float(within_50pct),
    'n_features': len(all_feats),
    'target_desc': {'min': float(agg['target'].min()), 'max': float(agg['target'].max()),
                    'mean': float(agg['target'].mean()), 'median': float(agg['target'].median())},
    'trained_at': datetime.now().isoformat(),
}
with open('trend_regression_model_meta.json', 'w', encoding='utf-8') as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

print(f"\n妯″瀷宸蹭繚瀛? trend_regression_model.json")
print(f"娴嬭瘯闆?R2(log)={test_r2:.4f}, MAE={test_mae:.0f}, MedAE={test_medae:.0f}, MAPE={test_mape:.1f}%")
print(f"璇樊<30%: {within_30pct:.1f}%, 璇樊<50%: {within_50pct:.1f}%")
