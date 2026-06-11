"""
XGBoost 鍥炲綊 鈥?12h 绐楀彛棰勬祴 log_hot (缁濆鍊?
浠庨娴嬪€兼帹瀵兼定璺岃秼鍔垮拰棰勮
"""
import json, warnings
import numpy as np
import pandas as pd
import pymysql
from datetime import datetime
from sklearn.preprocessing import RobustScaler, LabelEncoder
from sklearn.feature_selection import SelectKBest, mutual_info_classif
from sklearn.metrics import r2_score, mean_absolute_error
from xgboost import XGBRegressor
import lightgbm as lgb

warnings.filterwarnings('ignore')

TRAIN_END = '2026-03-01'
VAL_END = '2026-04-01'

def p(*args, **kwargs):
    print(*args, **kwargs, flush=True)

p(f"[{datetime.now():%H:%M:%S}] 杩炴帴鏁版嵁搴?..")
conn = pymysql.connect(host='<SERVER_IP>', port=3306, user='spark',
                       password = <DB_PASSWORD>, database='standardized_data',
                       charset='utf8mb4')
df = pd.read_sql("SELECT * FROM standardized_data WHERE publish_time >= '2022-01-01' ORDER BY keyword, publish_time", conn)
conn.close()
p(f"鍏?{len(df)} 鏉¤褰?)

# ========= 鑱氬悎 12h =========
df['publish_time'] = pd.to_datetime(df['publish_time'])
df['window_start'] = df['publish_time'].dt.floor('12H')

agg = df.groupby(['keyword', 'window_start']).agg(
    total_hot=('hot_score', 'sum'),
    count=('id', 'count'),
    avg_sentiment=('sentiment_score', 'mean'),
    total_like=('like_count', 'sum'),
    total_comment=('comment_count', 'sum'),
    total_view=('view_count', 'sum'),
    total_coin=('coin_count', 'sum'),
    total_favorite=('favorite_count', 'sum'),
    total_share=('share_count', 'sum'),
).reset_index().sort_values(['keyword', 'window_start'])

p(f"绐楀彛鏁? {len(agg)}")

# ========= 鐗瑰緛 =========
# log_hot (鐩爣)
agg['log_hot'] = np.log1p(agg['total_hot'])
agg['log_count'] = np.log1p(agg['count'])
agg['log_view'] = np.log1p(agg['total_view'])

# 鏃堕棿
agg['hour'] = agg['window_start'].dt.hour
agg['day_of_week'] = agg['window_start'].dt.dayofweek
agg['is_weekend'] = (agg['day_of_week'] >= 5).astype(int)
agg['month'] = agg['window_start'].dt.month

# 婊炲悗鐗瑰緛锛歭og_hot (鍒╃敤 0.6 鑷浉鍏?
for i in [1, 2, 3, 4, 5, 6, 7]:
    agg[f'lag_{i}_log_hot'] = agg.groupby('keyword')['log_hot'].shift(i)
    agg[f'lag_{i}_log_count'] = agg.groupby('keyword')['log_count'].shift(i)
    agg[f'lag_{i}_avg_sentiment'] = agg.groupby('keyword')['avg_sentiment'].shift(i)

# 鍛ㄦ湡鎬х壒寰侊細鏄ㄥぉ鍚屼竴鏃堕棿
agg['lag_2_log_hot_diff'] = agg['lag_2_log_hot'] - agg['lag_4_log_hot']  # 24h鍙樺寲瓒嬪娍

# 婊氬姩缁熻
for w in [2, 4, 6]:  # 24h, 48h, 72h
    r = agg.groupby('keyword')['log_hot'].rolling(w)
    agg[f'rm_{w}_log_hot'] = r.mean().reset_index(level=0, drop=True)
    agg[f'rmax_{w}_log_hot'] = r.max().reset_index(level=0, drop=True)

# 涓庡巻鍙插潎鍊肩殑瀵规瘮
for w in [2, 4, 6]:
    agg[f'hot_vs_rm{w}'] = agg['log_hot'] - agg[f'rm_{w}_log_hot']

# 鍙樺寲閲?agg['delta_lag1'] = agg.groupby('keyword')['log_hot'].diff(1).fillna(0)

# 鎯呮劅鐗瑰緛
agg['sentiment_ma2'] = agg.groupby('keyword')['avg_sentiment'].rolling(2).mean().reset_index(level=0, drop=True)

# ========= Target =========
TARGET = 'target_log_hot'
agg[TARGET] = agg.groupby('keyword')['log_hot'].shift(-1)
agg = agg.dropna(subset=[TARGET])

p(f"鏈夋晥鏍锋湰: {len(agg)}")

# ========= 鐗瑰緛鍒?=========
exclude = {'keyword', 'window_start', 'total_hot', 'count', 'total_like', 'total_comment',
           'total_view', 'total_coin', 'total_favorite', 'total_share', TARGET}
all_feats = [c for c in agg.columns if c not in exclude and agg[c].dtype in ('float64', 'int64', 'float32', 'int32')]
agg = agg.fillna(0).replace([np.inf, -np.inf], 0)

p(f"鐗瑰緛鏁? {len(all_feats)}")

# ========= 鏃堕棿鍒掑垎 =========
p(f"\n鍒掑垎: 璁粌 < {TRAIN_END}, 楠岃瘉 {TRAIN_END}~{VAL_END}, 娴嬭瘯 >= {VAL_END}")

train = agg[agg['window_start'] < TRAIN_END]
val = agg[(agg['window_start'] >= TRAIN_END) & (agg['window_start'] < VAL_END)]
test = agg[agg['window_start'] >= VAL_END]
p(f"璁粌={len(train)}, 楠岃瘉={len(val)}, 娴嬭瘯={len(test)}")

X_train, y_train = train[all_feats].copy(), train[TARGET].copy()
X_val, y_val = val[all_feats].copy(), val[TARGET].copy()
X_test, y_test = test[all_feats].copy(), test[TARGET].copy()

# ========= 璁粌 =========
model = XGBRegressor(
    n_estimators=2000, learning_rate=0.03, max_depth=8,
    subsample=0.8, colsample_bytree=0.8,
    reg_lambda=5, reg_alpha=2, min_child_weight=3,
    random_state=42, early_stopping_rounds=100,
    eval_metric='mae'
)

model.fit(X_train, y_train,
          eval_set=[(X_train, y_train), (X_val, y_val)],
          verbose=100)

# ========= 璇勪及 =========
for name, X, y in [('璁粌', X_train, y_train), ('楠岃瘉', X_val, y_val), ('娴嬭瘯', X_test, y_test)]:
    pred = model.predict(X)
    r2 = r2_score(y, pred)
    mae = mean_absolute_error(y, pred)
    rmse = np.sqrt(np.mean((pred - y) ** 2))

    # 鏂瑰悜鍑嗙‘鐜囷紙娑?璺岋級
    real_changes = y.values - X['log_hot'].values
    pred_changes = pred - X['log_hot'].values
    direction_acc = np.mean((pred_changes > 0) == (real_changes > 0)) * 100

    # 鏆存定棰勮锛氶娴嬪€?> 鍘嗗彶 P90
    train_p90 = y_train.quantile(0.90)
    pred_boom = (pred > train_p90).astype(int)
    real_boom = (y > train_p90).astype(int)
    boom_acc = np.mean(pred_boom == real_boom) * 100
    boom_recall = np.mean(pred_boom[real_boom == 1] == 1) * 100 if real_boom.sum() > 0 else 0
    boom_precision = np.mean(real_boom[pred_boom == 1] == 1) * 100 if pred_boom.sum() > 0 else 0

    p(f"\n  [{name}]")
    p(f"    R虏={r2:.4f}, MAE={mae:.4f}, RMSE={rmse:.4f}")
    p(f"    鏂瑰悜鍑嗙‘鐜?娑?璺?: {direction_acc:.1f}%")
    p(f"    鏆存定棰勮鍑嗙‘鐜? {boom_acc:.1f}%")
    p(f"    鏆存定鍙洖鐜? {boom_recall:.1f}%")
    p(f"    鏆存定绮剧‘鐜? {boom_precision:.1f}%")

# ========= 鎸夊叧閿瘝璇勪及 =========
p(f"\n{'='*50}")
p("鍚勫叧閿瘝娴嬭瘯闆嗚瘎浼?)
p(f"{'='*50}")
p(f"{'鍏抽敭璇?:<12} {'R虏':>7} {'MAE':>7} {'鏂瑰悜鍑嗙‘鐜?:>10}")
p("-"*38)
kw_results = []
for kw in sorted(test['keyword'].unique()):
    mask = test['keyword'] == kw
    Xk = test[mask][all_feats]
    yk = test[mask][TARGET]
    if len(yk) < 5:
        continue
    pk = model.predict(Xk)
    r2 = r2_score(yk, pk)
    mae = mean_absolute_error(yk, pk)
    real_ch = yk.values - Xk['log_hot'].values
    pred_ch = pk - Xk['log_hot'].values
    dir_acc = np.mean((pred_ch > 0) == (real_ch > 0)) * 100
    kw_results.append({'keyword': kw, 'r2': r2, 'mae': mae, 'dir_acc': dir_acc})
    p(f"  {kw:<12} {r2:>7.4f} {mae:>7.4f} {dir_acc:>8.1f}%")

avg_r2 = np.mean([r['r2'] for r in kw_results])
avg_mae = np.mean([r['mae'] for r in kw_results])
avg_dir = np.mean([r['dir_acc'] for r in kw_results])
p(f"\n  骞冲潎: R虏={avg_r2:.4f}, MAE={avg_mae:.4f}, 鏂瑰悜鍑嗙‘鐜?{avg_dir:.1f}%")

# ========= 娣锋穯鐭╅樀锛氭定璺岄娴?=========
p(f"\n{'='*50}")
p(f"娑ㄨ穼棰勬祴娣锋穯鐭╅樀 (娴嬭瘯闆?")
p(f"{'='*50}")

# 鍏ㄥ眬闃堝€?test_pred = model.predict(X_test)
test_real_ch = y_test.values - X_test['log_hot'].values
test_pred_ch = test_pred - X_test['log_hot'].values

# 娑?璺?浜屽垎绫绘柟鍚?from sklearn.metrics import confusion_matrix, classification_report
true_dir = (test_real_ch > 0).astype(int)
pred_dir = (test_pred_ch > 0).astype(int)
cm = confusion_matrix(true_dir, pred_dir)
p(f"  0=璺? 1=娑?)
p(f"  Confusion Matrix:\n{cm}")
tn, fp, fn, tp = cm.ravel()
p(f"  娑ㄩ娴嬪噯纭巼: {tp/(tp+fp)*100:.1f}%" if (tp+fp) > 0 else "  鏃?)
p(f"  璺岄娴嬪噯纭巼: {tn/(tn+fn)*100:.1f}%" if (tn+fn) > 0 else "  鏃?)
p(f"  鏁翠綋鏂瑰悜鍑嗙‘鐜? {(tp+tn)/(tp+tn+fp+fn)*100:.1f}%")

# 鏆存定/鏆磋穼/骞崇ǔ涓夊垎绫?q20, q80 = agg['change_rate'].quantile([0.20, 0.80]) if 'change_rate' in agg.columns else (-0.5, 1.0)
# 鐢?log_hot 鍙樺寲閲忓畾涔変笁妗?cr_test = test_real_ch  # log_hot 鍙樺寲閲?cr_pred = test_pred_ch

# 鐢ㄧ湡瀹炴暟鎹殑鍒嗕綅鏁?q20_real = np.percentile(cr_test, 20)
q80_real = np.percentile(cr_test, 80)

true_3 = np.zeros(len(cr_test), dtype=int)
true_3[cr_test > q80_real] = 2
true_3[cr_test < q20_real] = 0
true_3[(cr_test >= q20_real) & (cr_test <= q80_real)] = 1

pred_3 = np.zeros(len(cr_pred), dtype=int)
pred_3[cr_pred > q80_real] = 2
pred_3[cr_pred < q20_real] = 0
pred_3[(cr_pred >= q20_real) & (cr_pred <= q80_real)] = 1

cm_3 = confusion_matrix(true_3, pred_3)
acc_3 = np.mean(true_3 == pred_3) * 100
p(f"\n  涓夊垎绫?鏆磋穼/骞崇ǔ/鏆存定) 鍑嗙‘鐜? {acc_3:.1f}%")
p(f"  Confusion Matrix:\n{cm_3}")
p(f"\n  Classification Report:")
p(classification_report(true_3, pred_3, target_names=['鏆磋穼', '骞崇ǔ', '鏆存定']))

# ========= 淇濆瓨 =========
BASE_DIR = os.path.join(os.path.dirname(__file__), 'model_training')
model.save_model(f'{BASE_DIR}\\reg_12h_model.json')

meta = {
    'model_type': 'xgboost_regression',
    'window_size': '12H',
    'target': 'log_hot (shift -1)',
    'feature_columns': all_feats,
    'test_r2': float(avg_r2),
    'test_mae': float(avg_mae),
    'direction_accuracy': float(avg_dir),
    '3class_accuracy': float(acc_3),
    'train_split': f'< {TRAIN_END}',
    'val_split': f'{TRAIN_END} ~ {VAL_END}',
    'test_split': f'>= {VAL_END}',
    'train_samples': len(train),
    'test_samples': len(test),
    'n_features': len(all_feats),
    'per_keyword': kw_results,
    '3class_confusion_matrix': cm_3.tolist(),
    'direction_confusion_matrix': cm.tolist(),
    'trained_at': datetime.now().isoformat(),
}
with open(f'{BASE_DIR}\\reg_12h_model_meta.json', 'w', encoding='utf-8') as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

p(f"\n妯″瀷: {BASE_DIR}\\reg_12h_model.json")
p(f"鍏冩暟鎹? {BASE_DIR}\\reg_12h_model_meta.json")
p(f"娴嬭瘯闆?R虏={avg_r2:.4f}, 鏂瑰悜鍑嗙‘鐜?{avg_dir:.1f}%, 3鍒嗙被鍑嗙‘鐜?{acc_3:.1f}%")
