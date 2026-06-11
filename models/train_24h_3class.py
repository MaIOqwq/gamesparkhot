"""
24h 绐楀彛 3鍒嗙被娑?璺?骞崇ǔ
- 24h绐楀彛鑱氬悎锛屽埄鐢ㄦ棩鍛ㄦ湡
- 卤50% 鍙樺寲鐜囦綔涓烘定璺岄槇鍊?- XGBoost 鐩存帴鍒嗙被
"""
import json, warnings
import numpy as np
import pandas as pd
import pymysql
from datetime import datetime
from sklearn.preprocessing import RobustScaler
from sklearn.feature_selection import SelectKBest, mutual_info_classif
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report
from imblearn.over_sampling import SMOTE
from xgboost import XGBClassifier

warnings.filterwarnings('ignore')

TRAIN_END = '2026-04-01'
VAL_END = '2026-04-15'

def p(*args, **kwargs):
    print(*args, **kwargs, flush=True)

p(f"[{datetime.now():%H:%M:%S}] 杩炴帴鏁版嵁搴?..")
conn = pymysql.connect(host='<SERVER_IP>', port=3306, user='spark',
                       password = <DB_PASSWORD>, database='standardized_data', charset='utf8mb4')
df = pd.read_sql("SELECT * FROM standardized_data WHERE publish_time >= '2022-01-01' ORDER BY keyword, publish_time", conn)
conn.close()
p(f"鍏?{len(df)} 鏉¤褰?)

# 24h 鑱氬悎
df['publish_time'] = pd.to_datetime(df['publish_time'])
df['win'] = df['publish_time'].dt.floor('24H')

agg = df.groupby(['keyword', 'win']).agg(
    total_hot=('hot_score', 'sum'),
    count=('id', 'count'),
    avg_sentiment=('sentiment_score', 'mean'),
    total_like=('like_count', 'sum'),
    total_comment=('comment_count', 'sum'),
    avg_like=('like_count', 'mean'),
    avg_comment=('comment_count', 'mean'),
).reset_index().sort_values(['keyword', 'win'])

p(f"24h绐楀彛鏁? {len(agg)}")

# 鐗瑰緛
agg['log_hot'] = np.log1p(agg['total_hot'])
agg['log_count'] = np.log1p(agg['count'])
agg['day_of_week'] = agg['win'].dt.dayofweek
agg['month'] = agg['win'].dt.month

# 婊炲悗 (24h绐楀彛 鈥?鍓?澶?2澶?3澶?4澶?5澶?
for i in [1, 2, 3, 4, 5, 7]:
    agg[f'lag_{i}_log_hot'] = agg.groupby('keyword')['log_hot'].shift(i)
    agg[f'lag_{i}_log_count'] = agg.groupby('keyword')['log_count'].shift(i)
    agg[f'lag_{i}_sentiment'] = agg.groupby('keyword')['avg_sentiment'].shift(i)

# 婊氬姩缁熻 (3澶?7澶?14澶?
for w in [3, 7, 14]:
    r = agg.groupby('keyword')['log_hot'].rolling(w)
    agg[f'rm_{w}_log_hot'] = r.mean().reset_index(level=0, drop=True)
    agg[f'rmax_{w}_log_hot'] = r.max().reset_index(level=0, drop=True)
    agg[f'rstd_{w}_log_hot'] = r.std().reset_index(level=0, drop=True)

# 涓庡巻鍙插潎鍊煎亸宸?agg['hot_vs_rm3'] = agg['log_hot'] - agg['rm_3_log_hot']
agg['hot_vs_rm7'] = agg['log_hot'] - agg['rm_7_log_hot']

# 涓€鍛ㄥ墠鍚屾湡瀵规瘮
agg['dow7_diff'] = agg['lag_7_log_hot'] - agg['lag_14_log_hot'] if 'lag_14_log_hot' in agg.columns else 0

# ========= Label (鍥哄畾闃堝€? =========
agg['future_hot'] = agg.groupby('keyword')['total_hot'].shift(-1)
agg = agg.dropna(subset=['future_hot'])
agg['change_rate'] = (agg['future_hot'] - agg['total_hot']) / (agg['total_hot'] + 1e-6)

UP_THRESH = 0.50    # +50% 绠楁定
DOWN_THRESH = -0.30  # -30% 绠楄穼

agg['label'] = 1  # 骞崇ǔ
agg.loc[agg['change_rate'] > UP_THRESH, 'label'] = 2   # 娑?agg.loc[agg['change_rate'] < DOWN_THRESH, 'label'] = 0  # 璺?
for k, v in agg['label'].value_counts().sort_index().items():
    name = ['璺?, '骞崇ǔ', '娑?][k]
    p(f"  {name}: {v} ({v/len(agg)*100:.1f}%)")

# ========= 鍒掑垎 =========
all_feats = [c for c in agg.columns if c not in {'keyword', 'win', 'total_hot', 'count',
    'total_like', 'total_comment', 'avg_like', 'avg_comment', 'future_hot', 'change_rate', 'label'}
    and agg[c].dtype in ('float64', 'int64')]
agg = agg.fillna(0).replace([np.inf, -np.inf], 0)
p(f"鐗瑰緛鏁? {len(all_feats)}")

p(f"\n鍒掑垎: 璁粌<{TRAIN_END}, 楠岃瘉{TRAIN_END}~{VAL_END}, 娴嬭瘯>={VAL_END}")
train = agg[agg['win'] < TRAIN_END]
val = agg[(agg['win'] >= TRAIN_END) & (agg['win'] < VAL_END)]
test = agg[agg['win'] >= VAL_END]
p(f"璁粌={len(train)}, 楠岃瘉={len(val)}, 娴嬭瘯={len(test)}")

# ========= 璁粌 =========
# 鐗瑰緛閫夋嫨
selector = SelectKBest(mutual_info_classif, k=min(40, len(all_feats)))
selector.fit(train[all_feats], train['label'])
selected = [all_feats[i] for i in range(len(all_feats)) if selector.get_support()[i]]

scaler = RobustScaler()
X_train = scaler.fit_transform(train[selected])
X_val = scaler.transform(val[selected])
X_test = scaler.transform(test[selected])
y_train, y_val, y_test = train['label'], val['label'], test['label']

# SMOTE
smote = SMOTE(random_state=42, k_neighbors=3)
X_train_res, y_train_res = smote.fit_resample(X_train, y_train)
p(f"SMOTE: {len(X_train)} -> {len(X_train_res)}")

# 璁粌
model = XGBClassifier(
    objective='multi:softprob', num_class=3, eval_metric='mlogloss',
    max_depth=8, learning_rate=0.05, n_estimators=2000,
    subsample=0.8, colsample_bytree=0.8,
    reg_lambda=5, reg_alpha=2, min_child_weight=3,
    random_state=42, early_stopping_rounds=100
)
model.fit(X_train_res, y_train_res, eval_set=[(X_val, y_val)], verbose=100)

# ========= 璇勪及 =========
for name, X, y in [('璁粌', X_train, y_train), ('楠岃瘉', X_val, y_val), ('娴嬭瘯', X_test, y_test)]:
    pred = model.predict(X)
    acc = accuracy_score(y, pred) * 100
    cm = confusion_matrix(y, pred)
    p(f"\n[{name}] 鍑嗙‘鐜? {acc:.2f}%")
    p(f"Confusion Matrix:\n{cm}")
    if len(np.unique(y)) == 3:
        p(classification_report(y, pred, target_names=['璺?, '骞崇ǔ', '娑?]))

    # 鍚勯」鎸囨爣
    for i, label in enumerate(['璺?, '骞崇ǔ', '娑?]):
        if i < cm.shape[0] and i < cm.shape[1]:
            precision = cm[i,i] / cm[:,i].sum() * 100 if cm[:,i].sum() > 0 else 0
            recall = cm[i,i] / cm[i,:].sum() * 100 if cm[i,:].sum() > 0 else 0
            p(f"  {label}: 绮剧‘鐜?{precision:.1f}% 鍙洖鐜?{recall:.1f}%")

# ========= 淇濆瓨 =========
import os
BASE_DIR = os.path.join(os.path.dirname(__file__), 'model_training')
model.save_model(f'{BASE_DIR}\\trend_24h_3class_model.json')

meta = {
    'window': '24H',
    'model': 'XGBClassifier',
    'features': selected,
    'thresholds': {'娑?: f'change_rate > {UP_THRESH*100:.0f}%', '璺?: f'change_rate < {DOWN_THRESH*100:.0f}%'},
    'distribution': {k: int(v) for k, v in agg['label'].value_counts().to_dict().items()},
    'test_accuracy': float(accuracy_score(y_test, model.predict(X_test)) * 100),
    'test_confusion_matrix': confusion_matrix(y_test, model.predict(X_test)).tolist(),
    'train_samples': len(train),
    'test_samples': len(test),
}
with open(f'{BASE_DIR}\\trend_24h_3class_meta.json', 'w', encoding='utf-8') as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

p(f"\n妯″瀷: {BASE_DIR}\\trend_24h_3class_model.json")
p(f"鍏冩暟鎹? {BASE_DIR}\\trend_24h_3class_meta.json")
p(f"娴嬭瘯闆嗗噯纭巼: {meta['test_accuracy']:.2f}%")
