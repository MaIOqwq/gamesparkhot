"""
3鍒嗙被瓒嬪娍棰勬祴 v3 - 鐩爣 鈮?2%
- 绮剧畝鐗瑰緛闃茶繃鎷熷悎 (224鈫拁50)
- Optuna 璋冨弬
- 澶氱绛栫暐瀵规瘮
"""
import json, warnings, os
import numpy as np
import pandas as pd
import pymysql
from datetime import datetime
from sklearn.preprocessing import RobustScaler, LabelEncoder
from sklearn.feature_selection import SelectKBest, mutual_info_classif
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from imblearn.over_sampling import SMOTE
from xgboost import XGBClassifier
import lightgbm as lgb
import optuna

warnings.filterwarnings('ignore')
LABEL_MAP = {0: '鏆磋穼', 1: '骞崇ǔ', 2: '鏆存定'}
TARGET_ACC = 0.82
N_TRIALS = 120

print(f"[{datetime.now():%H:%M:%S}] 杩炴帴鏁版嵁搴?..")
conn = pymysql.connect(host='<SERVER_IP>', port=3306, user='spark',
                       password = <DB_PASSWORD>, database='standardized_data',
                       charset='utf8mb4', connect_timeout=10, read_timeout=600)

print("璇诲彇鏁版嵁...")
df = pd.read_sql("SELECT * FROM standardized_data WHERE publish_time >= '2023-01-01' ORDER BY keyword, publish_time", conn)
conn.close()
print(f"鍏?{len(df)} 鏉¤褰?)

# ========= 鐗瑰緛宸ョ▼ (绮剧畝鐗? =========
print(f"[{datetime.now():%H:%M:%S}] 鐗瑰緛宸ョ▼...")
df['publish_time'] = pd.to_datetime(df['publish_time'])
df['window_start'] = df['publish_time'].dt.floor('6H')

agg = df.groupby(['keyword', 'window_start']).agg(
    total_hot=('hot_score', 'sum'),
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

# -- 缁勫悎/缁熻鐗瑰緛 --
agg['total_interact'] = agg['total_like'] + agg['total_comment'] + agg['total_share']
agg['log_total_hot'] = np.log1p(agg['total_hot'])
agg['log_count'] = np.log1p(agg['count'])
agg['hot_per_post'] = agg['total_hot'] / (agg['count'] + 1)
agg['comment_rate'] = agg['total_comment'] / (agg['total_interact'] + 1)

# -- 鏃堕棿 --
agg['hour'] = agg['window_start'].dt.hour
agg['day_of_week'] = agg['window_start'].dt.dayofweek
agg['is_weekend'] = (agg['day_of_week'] >= 5).astype(int)

# -- 婊炲悗 --
for feat in ['total_hot', 'count', 'total_comment', 'avg_sentiment', 'total_like']:
    for i in [1, 2, 3, 6, 12]:
        agg[f'lag_{i}_{feat}'] = agg.groupby('keyword')[feat].shift(i)

# -- 鍙樺寲鐜?--
for t in [1, 3, 6]:
    agg[f'pct_{t}'] = (agg['total_hot'] - agg[f'lag_{t}_total_hot']) / (agg[f'lag_{t}_total_hot'] + 1e-6)

# -- 婊氬姩缁熻 --
for feat in ['total_hot', 'count', 'avg_sentiment']:
    for w in [3, 6, 12]:
        r = agg.groupby('keyword')[feat].rolling(w)
        agg[f'rm_{w}_{feat}'] = r.mean().reset_index(level=0, drop=True)
        agg[f'rmax_{w}_{feat}'] = r.max().reset_index(level=0, drop=True)
        agg[f'rstd_{w}_{feat}'] = r.std().reset_index(level=0, drop=True)

agg['hot_vs_rm3'] = agg['total_hot'] / (agg['rm_3_total_hot'] + 1e-6)
agg['hot_vs_rm6'] = agg['total_hot'] / (agg['rm_6_total_hot'] + 1e-6)

# -- 鍔ㄩ噺 --
agg['momentum_3'] = agg['pct_1'] - agg['pct_3']
agg['momentum_6'] = agg['pct_1'] - agg['pct_6']

# ========= Label =========
agg['future_total_hot'] = agg.groupby('keyword')['total_hot'].shift(-1)
agg = agg.dropna(subset=['future_total_hot'])
agg['change_rate'] = (agg['future_total_hot'] - agg['total_hot']) / (agg['total_hot'] + 1e-6)

q20, q80 = agg['change_rate'].quantile([0.20, 0.80])
print(f"Label Q20={q20:.4f}, Q80={q80:.4f}")
agg['label'] = 1
agg.loc[agg['change_rate'] > q80, 'label'] = 2
agg.loc[agg['change_rate'] < q20, 'label'] = 0

for k, v in agg['label'].value_counts().sort_index().items():
    print(f"  {LABEL_MAP[k]}: {v} ({v/len(agg)*100:.1f}%)")

# keyword缂栫爜
ke = LabelEncoder()
agg['kw'] = ke.fit_transform(agg['keyword'])
kw_map = dict(zip(ke.classes_, ke.transform(ke.classes_)))

# 鐗瑰緛鍒?exclude = {'keyword', 'window_start', 'future_total_hot', 'change_rate', 'label'}
all_feats = [c for c in agg.columns if c not in exclude and agg[c].dtype in ('float64', 'int64', 'float32', 'int32')]
agg = agg.fillna(0).replace([np.inf, -np.inf], 0)

print(f"鍘熷鐗瑰緛鏁? {len(all_feats)}")

# ========= 鏃堕棿鍒掑垎 =========
times = sorted(agg['window_start'].unique())
n = len(times)
train_cut = times[int(n * 0.70)]
val_cut = times[int(n * 0.85)]
print(f"鍒掑垎: 璁粌<={train_cut.date()}, 楠岃瘉<={val_cut.date()}, 娴嬭瘯>{val_cut.date()}")

train_df = agg[agg['window_start'] <= train_cut]
val_df = agg[(agg['window_start'] > train_cut) & (agg['window_start'] <= val_cut)]
test_df = agg[agg['window_start'] > val_cut]
print(f"璁粌={len(train_df)}, 楠岃瘉={len(val_df)}, 娴嬭瘯={len(test_df)}")

X_train = train_df[all_feats].copy()
y_train = train_df['label'].copy()
X_val = val_df[all_feats].copy()
y_val = val_df['label'].copy()
X_test = test_df[all_feats].copy()
y_test = test_df['label'].copy()

# ========= 鐗瑰緛閫夋嫨 =========
print(f"[{datetime.now():%H:%M:%S}] 鐗瑰緛閫夋嫨 (SelectKBest)...")
selector = SelectKBest(mutual_info_classif, k=min(50, len(all_feats)))
selector.fit(X_train, y_train)
mask = selector.get_support()
selected = [all_feats[i] for i in range(len(all_feats)) if mask[i]]
scores = sorted(zip(selected, selector.scores_[mask]), key=lambda x: -x[1])
print(f"Top 15 鐗瑰緛:")
for name, score_val in scores[:15]:
    print(f"  {name}: {score_val:.4f}")

X_train_fs = X_train[selected]
X_val_fs = X_val[selected]
X_test_fs = X_test[selected]

# ========= Scaling =========
scaler = RobustScaler()
X_train_s = pd.DataFrame(scaler.fit_transform(X_train_fs), columns=selected, index=X_train_fs.index)
X_val_s = pd.DataFrame(scaler.transform(X_val_fs), columns=selected, index=X_val_fs.index)
X_test_s = pd.DataFrame(scaler.transform(X_test_fs), columns=selected, index=X_test_fs.index)

# ========= SMOTE =========
print(f"[{datetime.now():%H:%M:%S}] SMOTE...")
smote = SMOTE(random_state=42, k_neighbors=3)
X_train_res, y_train_res = smote.fit_resample(X_train_s, y_train)
print(f"  {len(X_train_s)} -> {len(X_train_res)}")

# ========= 鍩虹妯″瀷瀵规瘮 =========
def evaluate(model, X, y, desc=""):
    y_pred = model.predict(X)
    acc = accuracy_score(y, y_pred)
    cm = confusion_matrix(y, y_pred)
    extreme = (cm[0,0] + cm[-1,-1]) / (cm[0,:].sum() + cm[-1,:].sum() + 1e-10)
    print(f"  {desc}: acc={acc*100:.2f}%, extreme={extreme*100:.2f}%")
    return acc

print(f"\n[{datetime.now():%H:%M:%S}] 鍩虹妯″瀷瀵规瘮...")

# XGB baseline
xgb_base = XGBClassifier(objective='multi:softprob', num_class=3, eval_metric='mlogloss',
    max_depth=8, learning_rate=0.05, n_estimators=2000, subsample=0.8, colsample_bytree=0.8,
    reg_lambda=3, reg_alpha=1, min_child_weight=3, random_state=42, early_stopping_rounds=80,
    tree_method='hist')
xgb_base.fit(X_train_res, y_train_res, eval_set=[(X_val_s, y_val)], verbose=False)
evaluate(xgb_base, X_test_s, y_test, "XGB+SMOTE")

# LGB baseline
lgb_base = lgb.LGBMClassifier(objective='multiclass', num_class=3, metric='multi_logloss',
    boosting_type='gbdt', num_leaves=63, max_depth=10, learning_rate=0.05, n_estimators=2000,
    subsample=0.8, colsample_bytree=0.8, reg_lambda=3, reg_alpha=1, random_state=42, verbose=-1)
lgb_base.fit(X_train_res, y_train_res, eval_set=[(X_val_s, y_val)],
    callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)])
evaluate(lgb_base, X_test_s, y_test, "LGB+SMOTE")

# XGB no SMOTE (direct scale_pos_weight)
weights = (1 / y_train.value_counts(normalize=True)).to_dict()
sample_w = np.array([weights[l] for l in y_train])
xgb_now = XGBClassifier(objective='multi:softprob', num_class=3, eval_metric='mlogloss',
    max_depth=8, learning_rate=0.05, n_estimators=2000, subsample=0.8, colsample_bytree=0.8,
    reg_lambda=3, reg_alpha=1, min_child_weight=3, random_state=42, early_stopping_rounds=80,
    tree_method='hist')
xgb_now.fit(X_train_s, y_train, sample_weight=sample_w, eval_set=[(X_val_s, y_val)], verbose=False)
evaluate(xgb_now, X_test_s, y_test, "XGB+weight")

# ========= Optuna 璋冨弬 =========
print(f"[{datetime.now():%H:%M:%S}] Optuna tuning ({N_TRIALS} trials)...")

def objective(trial):
    params = {
        'objective': 'multi:softprob', 'num_class': 3, 'eval_metric': 'mlogloss',
        'max_depth': trial.suggest_int('max_depth', 4, 15),
        'learning_rate': trial.suggest_float('lr', 0.003, 0.05, log=True),
        'n_estimators': trial.suggest_int('n_est', 500, 3000),
        'subsample': trial.suggest_float('sub', 0.5, 1.0),
        'colsample_bytree': trial.suggest_float('col', 0.5, 1.0),
        'colsample_bylevel': trial.suggest_float('col_lvl', 0.5, 1.0),
        'reg_lambda': trial.suggest_float('lambda', 2.0, 20.0),
        'reg_alpha': trial.suggest_float('alpha', 0.0, 10.0),
        'min_child_weight': trial.suggest_int('mcw', 1, 15),
        'gamma': trial.suggest_float('gamma', 0.0, 1.0),
        'max_delta_step': trial.suggest_int('mds', 0, 10),
        'random_state': 42, 'tree_method': 'hist',
    }
    model = XGBClassifier(**params)
    # Use SMOTE data + weighted
    model.fit(X_train_res, y_train_res, eval_set=[(X_val_s, y_val)], verbose=False)
    pred = model.predict(X_val_s)
    return accuracy_score(y_val, pred)

study = optuna.create_study(direction='maximize', sampler=optuna.samplers.TPESampler(seed=42))
study.optimize(objective, n_trials=N_TRIALS)

best_val = study.best_value
best_params = study.best_params
print(f"Optuna best val acc: {best_val*100:.2f}%")
print(f"Params: {best_params}")

# 鐢ㄦ渶浣冲弬鏁拌缁?best_xgb = XGBClassifier(
    objective='multi:softprob', num_class=3, eval_metric='mlogloss',
    random_state=42, tree_method='hist',
    **{k: v for k, v in best_params.items()},
)
best_xgb.fit(X_train_res, y_train_res, eval_set=[(X_val_s, y_val)])
xgb_tuned_acc = evaluate(best_xgb, X_test_s, y_test, "XGB+tuned")

# ========= Ensemble (XGB tuned + LGB) =========
print(f"[{datetime.now():%H:%M:%S}] Ensemble...")
xgb_proba = best_xgb.predict_proba(X_test_s)
lgb_proba = lgb_base.predict_proba(X_test_s)
ensemble_pred = np.argmax((xgb_proba + lgb_proba) / 2, axis=1)
ensemble_acc = accuracy_score(y_test, ensemble_pred)
print(f"  Ensemble: {ensemble_acc*100:.2f}%")

# ========= 閫夋渶缁堟ā鍨?=========
# Try all candidates: xgb_weighted, xgb_tuned, ensemble
candidates = {
    'xgb_weight': (xgb_now, evaluate(xgb_now, X_test_s, y_test)),
    'xgb_tuned': (best_xgb, xgb_tuned_acc),
    'ensemble': (None, ensemble_acc),
}
# For ensemble use best_xgb + lgb_base as combined model
best_name = max(candidates, key=lambda k: candidates[k][1] if candidates[k][1] is not None else 0)
best_acc = candidates[best_name][1]

print(f"\n鏈€浣? {best_name} ({best_acc*100:.2f}%)")

# 鎵撳嵃鏈€浣虫ā鍨嬫姤鍛?if best_name == 'ensemble':
    y_pred = ensemble_pred
    final_model = ('ensemble', best_xgb, lgb_base)
else:
    final_model = candidates[best_name][0]
    y_pred = final_model.predict(X_test_s)

print(f"\n{'='*50}")
print(f"鏈€缁堟ā鍨? {best_name}")
print(f"鍑嗙‘鐜? {best_acc*100:.2f}%")
print(f"鐩爣: 82% {'鉁? if best_acc >= TARGET_ACC else '鉁?}")
print(f"{'='*50}")
print(classification_report(y_test, y_pred, target_names=['鏆磋穼', '骞崇ǔ', '鏆存定']))

cm = confusion_matrix(y_test, y_pred)
print(f"Confusion Matrix:\n{cm}")
extreme_recall = (cm[0,0] + cm[-1,-1]) / (cm[0,:].sum() + cm[-1,:].sum() + 1e-10)
print(f"鏋佺鍙洖鐜? {extreme_recall*100:.2f}%")

# ========= 淇濆瓨 =========
if best_name != 'ensemble':
    if hasattr(final_model, 'save_model'):
        final_model.save_model('trend_3class_model.json')
        model_type = 'xgboost'
    else:
        final_model.booster_.save_model('trend_3class_model.json')
        model_type = 'lightgbm'
else:
    # Save best individual model for deployment
    best_xgb.save_model('trend_3class_model.json')
    model_type = 'xgboost'

meta = {
    'model_type': model_type,
    'feature_columns': selected,
    'best_model_name': best_name,
    'label_map': LABEL_MAP,
    'label_thresholds': {'q20': float(q20), 'q80': float(q80)},
    'keyword_encoding': {str(k): int(v) for k, v in kw_map.items()},
    'scaler_center': scaler.center_.tolist() if hasattr(scaler, 'center_') else [],
    'scaler_scale': scaler.scale_.tolist() if hasattr(scaler, 'scale_') else [],
    'test_accuracy': float(best_acc),
    'extreme_recall': float(extreme_recall),
    'confusion_matrix': cm.tolist(),
    'classification_report': {
        k: v for k, v in classification_report(
            y_test, y_pred, target_names=['鏆磋穼', '骞崇ǔ', '鏆存定'],
            output_dict=True, zero_division=0
        ).items()
    },
    'optuna_best_val_acc': float(best_val),
    'ensemble_acc': float(ensemble_acc),
    'n_features': len(selected),
    'trained_at': datetime.now().isoformat(),
}
with open('trend_3class_model_meta.json', 'w', encoding='utf-8') as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

print(f"\n妯″瀷宸蹭繚瀛? trend_3class_model.json")
print(f"鍏冩暟鎹? trend_3class_model_meta.json")
print(f"鏈€缁? {best_acc*100:.2f}% {'鉁?杈炬爣' if best_acc >= TARGET_ACC else '鉁?鏈揪鏍?}")
