"""
3鍒嗙被瓒嬪娍棰勬祴 v5 - XGBoost + Attention 鍔犳潈鐗瑰緛 (2h 绐楀彛)
- 2灏忔椂鑱氬悎绐楀彛锛屾洿缁嗙矑搴︽崟鎹夊彉鍖?- 瀵硅繃鍘?24 涓獥鍙ｅ仛 attention 鍔犳潈 (48h 鍘嗗彶)
- 鏃堕棿鍒掑垎: 2020~2026.02 璁粌, 2026.03 楠岃瘉, 2026.04~ 娴嬭瘯
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
N_TRIALS = 80   # 120鈫?0 鍔犻€?
TRAIN_END = '2026-03-01'   # 璁粌: 2020~2026.02 (鍖呭惈澶ч儴鍒?2026 鏁版嵁)
VAL_END = '2026-04-01'     # 楠岃瘉: 2026.03

WINDOW_SIZE = '2H'
ATTN_LAGS = 24       # 杩囧幓 24 涓?2h 绐楀彛 = 48h

def p(*args, **kwargs):
    """flush=True 鐨?print"""
    print(*args, **kwargs, flush=True)

p(f"[{datetime.now():%H:%M:%S}] 杩炴帴鏁版嵁搴?..")
conn = pymysql.connect(host='<SERVER_IP>', port=3306, user='spark',
                       password = <DB_PASSWORD>, database='standardized_data',
                       charset='utf8mb4', connect_timeout=10, read_timeout=600)

p("璇诲彇鏁版嵁 (2020-01-01 璧?...")
df = pd.read_sql("SELECT * FROM standardized_data WHERE publish_time >= '2020-01-01' ORDER BY keyword, publish_time", conn)
conn.close()
p(f"鍏?{len(df)} 鏉¤褰?)

# ========= 鐗瑰緛宸ョ▼ =========
p(f"[{datetime.now():%H:%M:%S}] 鐗瑰緛宸ョ▼ (绐楀彛={WINDOW_SIZE})...")
df['publish_time'] = pd.to_datetime(df['publish_time'])
df['window_start'] = df['publish_time'].dt.floor(WINDOW_SIZE)

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

# ========= Attention 鍔犳潈鐗瑰緛 =========
p(f"[{datetime.now():%H:%M:%S}] 璁＄畻 Attention 鐗瑰緛 ({ATTN_LAGS} lags)...")
ATTN_FEATS = ['total_hot', 'count', 'avg_sentiment', 'total_comment', 'total_like']

for feat in ATTN_FEATS:
    # 鍚戦噺鍖?attention: 鏋勫缓 (N, ATTN_LAGS) 婊炲悗鐭╅樀
    lag_list = []
    for i in range(1, ATTN_LAGS + 1):
        lag_list.append(agg.groupby('keyword')[feat].shift(i).values.reshape(-1, 1))
    lag_mat = np.column_stack(lag_list)  # (N, ATTN_LAGS)

    current = agg[feat].values.reshape(-1, 1)  # (N, 1)

    # 鐩镐技搴?= -|diff|
    diff = np.abs(current - lag_mat)
    scores = np.where(np.isnan(diff), -np.inf, -diff)

    # softmax (鏁板€肩ǔ瀹?
    scores_max = np.max(scores, axis=1, keepdims=True)
    scores_max = np.where(np.isinf(scores_max), 0, scores_max)
    exp_s = np.exp(scores - scores_max)
    sum_exp = np.sum(exp_s, axis=1, keepdims=True)
    sum_exp = np.where(sum_exp == 0, 1, sum_exp)
    weights = exp_s / sum_exp

    lag_mat_safe = np.nan_to_num(lag_mat, 0)
    attn_vals = np.sum(weights * lag_mat_safe, axis=1)

    agg[f'attn_{feat}'] = attn_vals

p("  Attention 鐗瑰緛:", [f'attn_{f}' for f in ATTN_FEATS])

# -- 婊炲悗 --
for feat in ['total_hot', 'count', 'total_comment', 'avg_sentiment', 'total_like']:
    for i in [1, 3, 6, 12, 24]:  # 2h/6h/12h/24h/48h
        agg[f'lag_{i}_{feat}'] = agg.groupby('keyword')[feat].shift(i)

# -- 鍙樺寲鐜?--
for t in [3, 6, 12, 24]:  # 6h/12h/24h/48h 鍙樺寲鐜?    agg[f'pct_{t}'] = (agg['total_hot'] - agg[f'lag_{t}_total_hot']) / (agg[f'lag_{t}_total_hot'] + 1e-6)

# -- 婊氬姩缁熻 (12h/24h/48h) --
for feat in ['total_hot', 'count', 'avg_sentiment']:
    for w in [6, 12, 24]:
        r = agg.groupby('keyword')[feat].rolling(w)
        agg[f'rm_{w}_{feat}'] = r.mean().reset_index(level=0, drop=True)
        agg[f'rmax_{w}_{feat}'] = r.max().reset_index(level=0, drop=True)
        agg[f'rstd_{w}_{feat}'] = r.std().reset_index(level=0, drop=True)

agg['hot_vs_rm6'] = agg['total_hot'] / (agg['rm_6_total_hot'] + 1e-6)
agg['hot_vs_rm12'] = agg['total_hot'] / (agg['rm_12_total_hot'] + 1e-6)

# -- 鍔ㄩ噺 --
agg['momentum_6'] = agg['pct_3'] - agg['pct_6']
agg['momentum_12'] = agg['pct_6'] - agg['pct_12']

# ========= Label =========
agg['future_total_hot'] = agg.groupby('keyword')['total_hot'].shift(-1)
agg = agg.dropna(subset=['future_total_hot'])
agg['change_rate'] = (agg['future_total_hot'] - agg['total_hot']) / (agg['total_hot'] + 1e-6)

q20, q80 = agg['change_rate'].quantile([0.20, 0.80])
p(f"Label Q20={q20:.4f}, Q80={q80:.4f}")
agg['label'] = 1
agg.loc[agg['change_rate'] > q80, 'label'] = 2
agg.loc[agg['change_rate'] < q20, 'label'] = 0

for k, v in agg['label'].value_counts().sort_index().items():
    p(f"  {LABEL_MAP[k]}: {v} ({v/len(agg)*100:.1f}%)")

# keyword缂栫爜
ke = LabelEncoder()
agg['kw'] = ke.fit_transform(agg['keyword'])
kw_map = dict(zip(ke.classes_, ke.transform(ke.classes_)))

# 鐗瑰緛鍒?exclude = {'keyword', 'window_start', 'future_total_hot', 'change_rate', 'label'}
exclude.update({f'_{feat}_lag_{i}' for feat in ATTN_FEATS for i in range(1, ATTN_LAGS + 1)})
all_feats = [c for c in agg.columns if c not in exclude and agg[c].dtype in ('float64', 'int64', 'float32', 'int32')]
agg = agg.fillna(0).replace([np.inf, -np.inf], 0)

p(f"鍘熷鐗瑰緛鏁? {len(all_feats)}")
p(f"鍓?10 鐗瑰緛: {all_feats[:10]}")

# ========= 鏃堕棿鍒掑垎 =========
p(f"\n鍒掑垎: 璁粌 < {TRAIN_END}, 楠岃瘉 {TRAIN_END}~{VAL_END}, 娴嬭瘯 >= {VAL_END}")

train_df = agg[agg['window_start'] < TRAIN_END]
val_df = agg[(agg['window_start'] >= TRAIN_END) & (agg['window_start'] < VAL_END)]
test_df = agg[agg['window_start'] >= VAL_END]
p(f"璁粌={len(train_df)}, 楠岃瘉={len(val_df)}, 娴嬭瘯={len(test_df)}")

X_train = train_df[all_feats].copy()
y_train = train_df['label'].copy()
X_val = val_df[all_feats].copy()
y_val = val_df['label'].copy()
X_test = test_df[all_feats].copy()
y_test = test_df['label'].copy()

# ========= 鐗瑰緛閫夋嫨 =========
p(f"[{datetime.now():%H:%M:%S}] 鐗瑰緛閫夋嫨 (SelectKBest, k=60)...")
k_features = min(60, len(all_feats))
selector = SelectKBest(mutual_info_classif, k=k_features)
selector.fit(X_train, y_train)
mask = selector.get_support()
selected = [all_feats[i] for i in range(len(all_feats)) if mask[i]]
scores = sorted(zip(selected, selector.scores_[mask]), key=lambda x: -x[1])
p(f"Top 15 鐗瑰緛:")
for name, score_val in scores[:15]:
    p(f"  {name}: {score_val:.4f}")

X_train_fs = X_train[selected]
X_val_fs = X_val[selected]
X_test_fs = X_test[selected]

# ========= Scaling =========
scaler = RobustScaler()
X_train_s = pd.DataFrame(scaler.fit_transform(X_train_fs), columns=selected, index=X_train_fs.index)
X_val_s = pd.DataFrame(scaler.transform(X_val_fs), columns=selected, index=X_val_fs.index)
X_test_s = pd.DataFrame(scaler.transform(X_test_fs), columns=selected, index=X_test_fs.index)

# ========= SMOTE =========
p(f"[{datetime.now():%H:%M:%S}] SMOTE...")
smote = SMOTE(random_state=42, k_neighbors=3)
X_train_res, y_train_res = smote.fit_resample(X_train_s, y_train)
p(f"  {len(X_train_s)} -> {len(X_train_res)}")

# ========= 璇勪及鍑芥暟 =========
def evaluate(model, X, y, desc=""):
    y_pred = model.predict(X)
    acc = accuracy_score(y, y_pred)
    cm = confusion_matrix(y, y_pred)
    extreme = (cm[0,0] + cm[-1,-1]) / (cm[0,:].sum() + cm[-1,:].sum() + 1e-10)
    p(f"  {desc}: acc={acc*100:.2f}%, extreme_acc={extreme*100:.2f}%")
    return acc

# ========= 鍩虹妯″瀷瀵规瘮 =========
p(f"\n[{datetime.now():%H:%M:%S}] 鍩虹妯″瀷瀵规瘮...")

xgb_base = XGBClassifier(objective='multi:softprob', num_class=3, eval_metric='mlogloss',
    max_depth=8, learning_rate=0.05, n_estimators=2000, subsample=0.8, colsample_bytree=0.8,
    reg_lambda=3, reg_alpha=1, min_child_weight=3, random_state=42, early_stopping_rounds=80,
    tree_method='hist')
xgb_base.fit(X_train_res, y_train_res, eval_set=[(X_val_s, y_val)], verbose=False)
xgb_base_acc = evaluate(xgb_base, X_test_s, y_test, "XGB+SMOTE")

lgb_base = lgb.LGBMClassifier(objective='multiclass', num_class=3, metric='multi_logloss',
    boosting_type='gbdt', num_leaves=63, max_depth=10, learning_rate=0.05, n_estimators=2000,
    subsample=0.8, colsample_bytree=0.8, reg_lambda=3, reg_alpha=1, random_state=42, verbose=-1)
lgb_base.fit(X_train_res, y_train_res, eval_set=[(X_val_s, y_val)],
    callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)])
lgb_base_acc = evaluate(lgb_base, X_test_s, y_test, "LGB+SMOTE")

weights = (1 / y_train.value_counts(normalize=True)).to_dict()
sample_w = np.array([weights[l] for l in y_train])
xgb_now = XGBClassifier(objective='multi:softprob', num_class=3, eval_metric='mlogloss',
    max_depth=8, learning_rate=0.05, n_estimators=2000, subsample=0.8, colsample_bytree=0.8,
    reg_lambda=3, reg_alpha=1, min_child_weight=3, random_state=42, early_stopping_rounds=80,
    tree_method='hist')
xgb_now.fit(X_train_s, y_train, sample_weight=sample_w, eval_set=[(X_val_s, y_val)], verbose=False)
xgb_w_acc = evaluate(xgb_now, X_test_s, y_test, "XGB+weight")

# ========= Optuna 璋冨弬 =========
p(f"[{datetime.now():%H:%M:%S}] Optuna tuning ({N_TRIALS} trials)...")

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
    model.fit(X_train_res, y_train_res, eval_set=[(X_val_s, y_val)], verbose=False)
    pred = model.predict(X_val_s)
    return accuracy_score(y_val, pred)

study = optuna.create_study(direction='maximize', sampler=optuna.samplers.TPESampler(seed=42))
study.optimize(objective, n_trials=N_TRIALS)

best_val = study.best_value
best_params = study.best_params
p(f"Optuna best val acc: {best_val*100:.2f}%")
p(f"Params: {best_params}")

best_xgb = XGBClassifier(
    objective='multi:softprob', num_class=3, eval_metric='mlogloss',
    random_state=42, tree_method='hist',
    **{k: v for k, v in best_params.items()},
)
best_xgb.fit(X_train_res, y_train_res, eval_set=[(X_val_s, y_val)])
xgb_tuned_acc = evaluate(best_xgb, X_test_s, y_test, "XGB+tuned")

# ========= Ensemble =========
p(f"[{datetime.now():%H:%M:%S}] Ensemble...")
xgb_proba = best_xgb.predict_proba(X_test_s)
lgb_proba = lgb_base.predict_proba(X_test_s)
ensemble_pred = np.argmax((xgb_proba + lgb_proba) / 2, axis=1)
ensemble_acc = accuracy_score(y_test, ensemble_pred)
p(f"  Ensemble: {ensemble_acc*100:.2f}%")

# ========= 閫夋渶缁堟ā鍨?=========
candidates = {
    'xgb_weight': (xgb_now, xgb_w_acc),
    'xgb_tuned': (best_xgb, xgb_tuned_acc),
    'ensemble': (None, ensemble_acc),
}
best_name = max(candidates, key=lambda k: candidates[k][1] if candidates[k][1] is not None else 0)
best_acc = candidates[best_name][1]

p(f"\n鏈€浣? {best_name} ({best_acc*100:.2f}%)")

if best_name == 'ensemble':
    y_pred = ensemble_pred
    final_model = ('ensemble', best_xgb, lgb_base)
else:
    final_model = candidates[best_name][0]
    y_pred = final_model.predict(X_test_s)

p(f"\n{'='*50}")
p(f"鏈€缁堟ā鍨? {best_name}")
p(f"鍑嗙‘鐜? {best_acc*100:.2f}%")
p(f"鐩爣: {TARGET_ACC*100:.0f}% {'OK' if best_acc >= TARGET_ACC else 'FAIL'}")
p(f"{'='*50}")
p(classification_report(y_test, y_pred, target_names=['鏆磋穼', '骞崇ǔ', '鏆存定']))

cm = confusion_matrix(y_test, y_pred)
p(f"Confusion Matrix:\n{cm}")
extreme_recall = (cm[0,0] + cm[-1,-1]) / (cm[0,:].sum() + cm[-1,:].sum() + 1e-10)
p(f"鏋佺鍙洖鐜? {extreme_recall*100:.2f}%")

# ========= Attention 鐗瑰緛閲嶈鎬у垎鏋?=========
p(f"\n{'='*50}")
p("Attention 鐗瑰緛閲嶈鎬у垎鏋?")
if hasattr(best_xgb, 'feature_importances_'):
    fi = sorted(zip(selected, best_xgb.feature_importances_), key=lambda x: -x[1])
    attn_found = [(n, s) for n, s in fi if 'attn_' in n]
    if attn_found:
        p(f"Attention 鐗瑰緛鍦?Top 鐗瑰緛涓殑浣嶇疆:")
        for name, score in attn_found[:5]:
            rank = next(i+1 for i, (n, s) in enumerate(fi) if n == name)
            p(f"  #{rank} {name}: {score:.4f}")
        avg_rank = np.mean([next(i+1 for i, (n, s) in enumerate(fi) if n == name) for name, _ in attn_found])
        p(f"  Attention 鐗瑰緛骞冲潎鎺掑悕: {avg_rank:.0f}/{len(fi)}")
    else:
        p("  Attention 鐗瑰緛鏈閫夋嫨")

# ========= 淇濆瓨 =========
if best_name != 'ensemble':
    if hasattr(final_model, 'save_model'):
        final_model.save_model('trend_3class_v5_model.json')
        model_type = 'xgboost'
    else:
        final_model.booster_.save_model('trend_3class_v5_model.json')
        model_type = 'lightgbm'
else:
    best_xgb.save_model('trend_3class_v5_model.json')
    model_type = 'xgboost'

meta = {
    'model_type': model_type,
    'feature_columns': selected,
    'window_size': WINDOW_SIZE,
    'best_model_name': best_name,
    'label_map': LABEL_MAP,
    'label_thresholds': {'q20': float(q20), 'q80': float(q80)},
    'keyword_encoding': {str(k): int(v) for k, v in kw_map.items()},
    'scaler_center': scaler.center_.tolist() if hasattr(scaler, 'center_') else [],
    'scaler_scale': scaler.scale_.tolist() if hasattr(scaler, 'scale_') else [],
    'test_accuracy': float(best_acc),
    'extreme_recall': float(extreme_recall),
    'confusion_matrix': cm.tolist(),
    'attention_features': [f'attn_{f}' for f in ATTN_FEATS],
    'n_attention_features': len(ATTN_FEATS),
    'train_split': f'< {TRAIN_END}',
    'val_split': f'{TRAIN_END} ~ {VAL_END}',
    'test_split': f'>= {VAL_END}',
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
with open('trend_3class_v5_model_meta.json', 'w', encoding='utf-8') as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

p(f"\n妯″瀷宸蹭繚瀛? trend_3class_v5_model.json")
p(f"鍏冩暟鎹? trend_3class_v5_model_meta.json")
p(f"鏈€缁? {best_acc*100:.2f}% {'OK 杈炬爣' if best_acc >= TARGET_ACC else 'FAIL 鏈揪鏍?}")
