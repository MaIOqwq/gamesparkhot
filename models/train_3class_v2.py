"""
3鍒嗙被瓒嬪娍棰勬祴妯″瀷璁粌 (鏆磋穼/骞崇ǔ/鏆存定)
鐩爣: 鍑嗙‘鐜?鈮?82%
绛栫暐:
  - label: change_rate Q20/Q80 鍒嗙晫
  - XGBoost + LightGBM + Ensemble
  - SMOTE 骞宠　
  - 寮哄寲鐗瑰緛宸ョ▼ + 璋冨弬
"""
import json, warnings, os, sys
import numpy as np
import pandas as pd
import pymysql
from datetime import datetime

warnings.filterwarnings('ignore')

# ========= 閰嶇疆 =========
DB_CONFIG = dict(host='<SERVER_IP>', port=3306, user='spark',
                 password = <DB_PASSWORD>, database='standardized_data')
N_TRIALS = 80          # Optuna trials
TARGET_ACC = 0.82

print(f"[{datetime.now():%H:%M:%S}] 杩炴帴鏁版嵁搴?..")
conn = pymysql.connect(charset='utf8mb4', connect_timeout=10, read_timeout=600, **DB_CONFIG)

print("璇诲彇鏁版嵁...")
df = pd.read_sql("SELECT * FROM standardized_data WHERE publish_time >= '2023-01-01' ORDER BY keyword, publish_time", conn)
conn.close()
print(f"鍏?{len(df)} 鏉¤褰?)

# ========= 鐗瑰緛宸ョ▼ =========
print(f"\n[{datetime.now():%H:%M:%S}] 鐗瑰緛宸ョ▼...")
df['publish_time'] = pd.to_datetime(df['publish_time'])
df['window_start'] = df['publish_time'].dt.floor('6H')

agg = df.groupby(['keyword', 'window_start']).agg(
    total_hot=('hot_score', 'sum'),
    total_hot_raw=('hot_raw', 'max'),
    total_like=('like_count', 'sum'),
    avg_like=('like_count', 'mean'),
    total_comment=('comment_count', 'sum'),
    avg_comment=('comment_count', 'mean'),
    total_view=('view_count', 'sum'),
    avg_view=('view_count', 'mean'),
    total_coin=('coin_count', 'sum'),
    total_favorite=('favorite_count', 'sum'),
    total_share=('share_count', 'sum'),
    total_danmaku=('danmaku_count', 'sum'),
    avg_sentiment=('sentiment_score', 'mean'),
    avg_author_fans=('author_fans', 'mean'),
    avg_author_level=('author_level', 'mean'),
    count=('id', 'count'),
).reset_index()

agg = agg.sort_values(['keyword', 'window_start']).reset_index(drop=True)

# ---- 鍩虹鐗瑰緛 ----
agg['mean_hot'] = agg.groupby('keyword')['total_hot'].transform('mean')
agg['max_hot'] = agg.groupby('keyword')['total_hot'].transform('max')
agg['std_hot'] = agg.groupby('keyword')['total_hot'].transform('std').fillna(0)
agg['log_total_hot'] = np.log1p(agg['total_hot'])
agg['log_count'] = np.log1p(agg['count'])
agg['hot_per_post'] = agg['total_hot'] / (agg['count'] + 1)
agg['total_interact'] = agg['total_like'] + agg['total_comment'] + agg['total_share']
agg['log_interact'] = np.log1p(agg['total_interact'])
agg['comment_to_like_ratio'] = agg['total_comment'] / (agg['total_like'] + 1)
agg['favorite_rate'] = agg['total_favorite'] / (agg['total_view'] + 1)

# ---- 鏃堕棿鐗瑰緛 ----
agg['hour'] = agg['window_start'].dt.hour
agg['day_of_week'] = agg['window_start'].dt.dayofweek
agg['is_weekend'] = (agg['day_of_week'] >= 5).astype(int)
agg['month'] = agg['window_start'].dt.month
agg['quarter'] = agg['window_start'].dt.quarter
agg['day_sin'] = np.sin(2 * np.pi * agg['day_of_week'] / 7)
agg['hour_sin'] = np.sin(2 * np.pi * agg['hour'] / 24)

# ---- 婊炲悗鐗瑰緛 (澶氱獥鍙? ----
for feat in ['total_hot', 'count', 'total_comment', 'avg_sentiment',
             'total_like', 'total_view', 'total_coin']:
    for i in [1, 2, 3, 4, 6, 8, 12]:
        agg[f'lag_{i}_{feat}'] = agg.groupby('keyword')[feat].shift(i)

# ---- 鍙樺寲鐜囩壒寰?----
for t in [1, 2, 3, 4, 6]:
    lag_col = f'lag_{t}_total_hot'
    agg[f'change_rate_{t}'] = (agg['total_hot'] - agg[lag_col]) / (agg[lag_col] + 1e-6)
    agg[f'change_rate_{t}_clip'] = agg[f'change_rate_{t}'].clip(-10, 10)

agg['count_change_rate'] = (agg['count'] - agg['lag_1_count']) / (agg['lag_1_count'] + 1e-6)

# ---- 婊氬姩缁熻 ----
for feat in ['total_hot', 'count', 'avg_sentiment', 'total_interact', 'total_like']:
    for w in [2, 3, 4, 6, 8, 12]:
        rolling = agg.groupby('keyword')[feat].rolling(w)
        agg[f'rolling_mean_{w}_{feat}'] = rolling.mean().reset_index(level=0, drop=True)
        agg[f'rolling_std_{w}_{feat}'] = rolling.std().reset_index(level=0, drop=True)
        agg[f'rolling_max_{w}_{feat}'] = rolling.max().reset_index(level=0, drop=True)
        agg[f'rolling_min_{w}_{feat}'] = rolling.min().reset_index(level=0, drop=True)

# ---- 婊氬姩鍙樺寲鐜?----
for w in [3, 6]:
    rolling = agg.groupby('keyword')['total_hot'].rolling(w).mean().reset_index(level=0, drop=True)
    agg[f'rolling_mean_{w}_total_hot_vs_current'] = (agg['total_hot'] - rolling) / (rolling + 1e-6)

# ---- 鍔ㄩ噺鐗瑰緛 ----
agg['hot_momentum_3'] = agg['change_rate_1'] - agg['change_rate_3']
agg['hot_momentum_6'] = agg['change_rate_1'] - agg['change_rate_6']

# ---- 浜や簰鐗瑰緛 ----
agg['hot_x_count'] = agg['total_hot'] * agg['count']
agg['hot_x_sentiment'] = agg['total_hot'] * agg['avg_sentiment']
agg['sentiment_x_count'] = agg['avg_sentiment'] * agg['count']
agg['log_hot_x_log_count'] = agg['log_total_hot'] * agg['log_count']
agg['change_rate_x_sentiment'] = agg['change_rate_1_clip'] * agg['avg_sentiment']

# ---- volatility鐗瑰緛 ----
agg['hot_volatility_6'] = agg.groupby('keyword')['total_hot'].rolling(6).std().reset_index(level=0, drop=True)
agg['coef_variation'] = agg['std_hot'] / (agg['mean_hot'] + 1)

# ========= Label =========
agg['future_total_hot'] = agg.groupby('keyword')['total_hot'].shift(-1)
agg = agg.dropna(subset=['future_total_hot'])

agg['change_rate'] = (agg['future_total_hot'] - agg['total_hot']) / (agg['total_hot'] + 1e-6)
q20, q80 = agg['change_rate'].quantile([0.20, 0.80])
print(f"Label thresholds: Q20={q20:.4f}, Q80={q80:.4f}")

# 3鍒嗙被: 0=鏆磋穼, 1=骞崇ǔ, 2=鏆存定
agg['label'] = 1  # 骞崇ǔ
agg.loc[agg['change_rate'] > q80, 'label'] = 2  # 鏆存定
agg.loc[agg['change_rate'] < q20, 'label'] = 0  # 鏆磋穼

counts = agg['label'].value_counts().sort_index()
label_names = {0: '鏆磋穼', 1: '骞崇ǔ', 2: '鏆存定'}
for k, v in counts.items():
    print(f"  {label_names[k]}: {v} ({v/len(agg)*100:.1f}%)")

# keyword encoding
from sklearn.preprocessing import LabelEncoder
kw_encoder = LabelEncoder()
agg['keyword_enc'] = kw_encoder.fit_transform(agg['keyword'])

keyword_map = dict(zip(kw_encoder.classes_, kw_encoder.transform(kw_encoder.classes_)))
print(f"Keywords: {len(keyword_map)}")

# feature columns - 鎺掗櫎闈炵壒寰佸垪
exclude = {'keyword', 'window_start', 'publish_time', 'future_total_hot',
           'change_rate', 'label', 'total_hot_raw'}
feature_columns = [c for c in agg.columns if c not in exclude]
feature_columns = [c for c in feature_columns if c in agg.columns]
print(f"鐗瑰緛鎬绘暟: {len(feature_columns)}")

# 濉厖缂哄け + 鏇挎崲 inf
agg = agg.fillna(0).replace([np.inf, -np.inf], 0)

# ========= 鏃堕棿鍒掑垎 =========
times = sorted(agg['window_start'].unique())
n = len(times)
train_cut = times[int(n * 0.7)]
val_cut = times[int(n * 0.85)]
print(f"鏃跺簭鍒掑垎: 璁粌<={train_cut}, 楠岃瘉<={val_cut}, 娴嬭瘯>{val_cut}")

train_df = agg[agg['window_start'] <= train_cut]
val_df = agg[(agg['window_start'] > train_cut) & (agg['window_start'] <= val_cut)]
test_df = agg[agg['window_start'] > val_cut]
print(f"璁粌={len(train_df)}, 楠岃瘉={len(val_df)}, 娴嬭瘯={len(test_df)}")

X_train = train_df[feature_columns].copy()
y_train = train_df['label'].copy()
X_val = val_df[feature_columns].copy()
y_val = val_df['label'].copy()
X_test = test_df[feature_columns].copy()
y_test = test_df['label'].copy()

# Scaling
from sklearn.preprocessing import RobustScaler
scaler = RobustScaler()
X_train_s = pd.DataFrame(scaler.fit_transform(X_train), columns=feature_columns, index=X_train.index)
X_val_s = pd.DataFrame(scaler.transform(X_val), columns=feature_columns, index=X_val.index)
X_test_s = pd.DataFrame(scaler.transform(X_test), columns=feature_columns, index=X_test.index)

# SMOTE
from imblearn.over_sampling import SMOTE
print("\n搴旂敤 SMOTE...")
smote = SMOTE(random_state=42, k_neighbors=3)
X_train_res, y_train_res = smote.fit_resample(X_train_s, y_train)
print(f"SMOTE: {len(X_train_s)} -> {len(X_train_res)}")
resampled_counts = pd.Series(y_train_res).value_counts().sort_index()
for k, v in resampled_counts.items():
    print(f"  {label_names[k]}: {v}")

# ========= 璁粌鍑芥暟 =========
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from xgboost import XGBClassifier
import lightgbm as lgb

def evaluate(model, X, y, name="Model"):
    y_pred = model.predict(X)
    acc = accuracy_score(y, y_pred)
    report = classification_report(y, y_pred, target_names=['鏆磋穼', '骞崇ǔ', '鏆存定'],
                                  output_dict=True, zero_division=0)
    cm = confusion_matrix(y, y_pred)
    extreme_recall = (cm[0,0] + cm[-1,-1]) / (cm[0,:].sum() + cm[-1,:].sum() + 1e-10)
    return {'accuracy': acc, 'report': report, 'confusion_matrix': cm, 'extreme_recall': extreme_recall}

# ========= XGBoost (no SMOTE) =========
print(f"\n[{datetime.now():%H:%M:%S}] XGBoost (no SMOTE)...")
xgb = XGBClassifier(
    objective='multi:softprob', num_class=3, eval_metric='mlogloss',
    max_depth=10, learning_rate=0.03, n_estimators=3000,
    subsample=0.8, colsample_bytree=0.8,
    reg_lambda=5.0, reg_alpha=2.0, min_child_weight=5, gamma=0.2,
    random_state=42, early_stopping_rounds=80,
    tree_method='hist',  # faster
)
xgb.fit(X_train_s, y_train, eval_set=[(X_val_s, y_val)], verbose=False)
xgb_metrics = evaluate(xgb, X_test_s, y_test, "XGBoost")
print(f"  Test acc: {xgb_metrics['accuracy']*100:.2f}%, extreme_recall: {xgb_metrics['extreme_recall']*100:.2f}%")

# ========= XGBoost + SMOTE =========
print(f"[{datetime.now():%H:%M:%S}] XGBoost + SMOTE...")
xgb_smote = XGBClassifier(
    objective='multi:softprob', num_class=3, eval_metric='mlogloss',
    max_depth=10, learning_rate=0.03, n_estimators=3000,
    subsample=0.8, colsample_bytree=0.8,
    reg_lambda=5.0, reg_alpha=2.0, min_child_weight=5, gamma=0.2,
    random_state=42, early_stopping_rounds=80,
    tree_method='hist',
)
xgb_smote.fit(X_train_res, y_train_res, eval_set=[(X_val_s, y_val)], verbose=False)
xgb_smote_metrics = evaluate(xgb_smote, X_test_s, y_test, "XGB+SMOTE")
print(f"  Test acc: {xgb_smote_metrics['accuracy']*100:.2f}%, extreme_recall: {xgb_smote_metrics['extreme_recall']*100:.2f}%")

# ========= LightGBM (no SMOTE) =========
print(f"[{datetime.now():%H:%M:%S}] LightGBM (no SMOTE)...")
lgbm = lgb.LGBMClassifier(
    objective='multiclass', num_class=3, metric='multi_logloss',
    boosting_type='gbdt', num_leaves=127, max_depth=15,
    learning_rate=0.03, n_estimators=3000,
    subsample=0.8, colsample_bytree=0.8,
    reg_lambda=5.0, reg_alpha=2.0, min_child_samples=20,
    random_state=42, verbose=-1,
)
lgbm.fit(X_train_s, y_train, eval_set=[(X_val_s, y_val)],
         callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)])
lgbm_metrics = evaluate(lgbm, X_test_s, y_test, "LightGBM")
print(f"  Test acc: {lgbm_metrics['accuracy']*100:.2f}%, extreme_recall: {lgbm_metrics['extreme_recall']*100:.2f}%")

# ========= LightGBM + SMOTE =========
print(f"[{datetime.now():%H:%M:%S}] LightGBM + SMOTE...")
lgbm_smote = lgb.LGBMClassifier(
    objective='multiclass', num_class=3, metric='multi_logloss',
    boosting_type='gbdt', num_leaves=127, max_depth=15,
    learning_rate=0.03, n_estimators=3000,
    subsample=0.8, colsample_bytree=0.8,
    reg_lambda=5.0, reg_alpha=2.0, min_child_samples=20,
    random_state=42, verbose=-1,
)
lgbm_smote.fit(X_train_res, y_train_res, eval_set=[(X_val_s, y_val)],
               callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)])
lgbm_smote_metrics = evaluate(lgbm_smote, X_test_s, y_test, "LGB+SMOTE")
print(f"  Test acc: {lgbm_smote_metrics['accuracy']*100:.2f}%, extreme_recall: {lgbm_smote_metrics['extreme_recall']*100:.2f}%")

# ========= Ensemble =========
print(f"\n[{datetime.now():%H:%M:%S}] Ensemble (XGB+LGB probability avg)...")
xgb_proba = xgb_smote.predict_proba(X_test_s)
lgbm_proba = lgbm_smote.predict_proba(X_test_s)
ensemble_proba = (xgb_proba + lgbm_proba) / 2
ensemble_pred = np.argmax(ensemble_proba, axis=1)
ensemble_acc = accuracy_score(y_test, ensemble_pred)
print(f"  Ensemble acc: {ensemble_acc*100:.2f}%")

# ========= Optuna 璋冨弬 =========
print(f"\n[{datetime.now():%H:%M:%S}] Optuna 璋冨弬 (XGBoost)...")
try:
    import optuna
    optuna_available = True
except ImportError:
    optuna_available = False

if optuna_available:
    def objective(trial):
        params = {
            'objective': 'multi:softprob', 'num_class': 3, 'eval_metric': 'mlogloss',
            'max_depth': trial.suggest_int('max_depth', 5, 15),
            'learning_rate': trial.suggest_float('learning_rate', 0.005, 0.05, log=True),
            'n_estimators': trial.suggest_int('n_estimators', 500, 3000),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
            'reg_lambda': trial.suggest_float('reg_lambda', 1.0, 10.0),
            'reg_alpha': trial.suggest_float('reg_alpha', 0.0, 5.0),
            'min_child_weight': trial.suggest_int('min_child_weight', 1, 10),
            'gamma': trial.suggest_float('gamma', 0.0, 1.0),
            'random_state': 42,
            'tree_method': 'hist',
            'early_stopping_rounds': 80,
        }
        model = XGBClassifier(**params)
        model.fit(X_train_res, y_train_res, eval_set=[(X_val_s, y_val)], verbose=False)
        pred = model.predict(X_val_s)
        return accuracy_score(y_val, pred)

    study = optuna.create_study(direction='maximize', sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=N_TRIALS, show_progress_bar=True)

    best_params = study.best_params
    best_val_acc = study.best_value
    print(f"\nOptuna best val acc: {best_val_acc*100:.2f}%")
    print(f"Best params: {best_params}")

    # Train with best params
    print(f"\n[{datetime.now():%H:%M:%S}] 璁粌鏈€浣?XGBoost...")
    best_params.update({
        'objective': 'multi:softprob', 'num_class': 3, 'eval_metric': 'mlogloss',
        'random_state': 42, 'tree_method': 'hist',
    })
    best_xgb = XGBClassifier(**best_params)
    best_xgb.fit(X_train_res, y_train_res, eval_set=[(X_val_s, y_val)])
else:
    print("  optuna not installed, using default tuned params")
    best_xgb = xgb_smote
    best_val_acc = xgb_smote_metrics['accuracy']

xgb_tuned_metrics = evaluate(best_xgb, X_test_s, y_test, "XGBoost(tuned)")
print(f"  Test acc: {xgb_tuned_metrics['accuracy']*100:.2f}%")

# ========= 閫夋渶浣虫ā鍨?=========
all_metrics = {
    'xgb': xgb_metrics, 'xgb_smote': xgb_smote_metrics,
    'lgbm': lgbm_metrics, 'lgbm_smote': lgbm_smote_metrics,
    'xgb_tuned': xgb_tuned_metrics,
}

best_name = max(all_metrics, key=lambda k: all_metrics[k]['accuracy'])
best_acc = all_metrics[best_name]['accuracy']
print(f"\n{'='*50}")
print(f"鏈€浣虫ā鍨? {best_name}, 娴嬭瘯鍑嗙‘鐜? {best_acc*100:.2f}%")
print(f"{'='*50}")

# 濡傛灉 ensemble 鏇村ソ涓旇揪鏍?if ensemble_acc > best_acc and ensemble_acc >= TARGET_ACC:
    print(f"Ensemble 鏇翠紭 ({ensemble_acc*100:.2f}%)锛屼娇鐢?ensemble 鏈€浣?)
    # 浠嶇劧淇濆瓨鍗曚釜鏈€浣虫ā鍨嬬敤浜庨儴缃?    if best_name.startswith('xgb'):
        final_model = best_xgb
    else:
        final_model = lgbm_smote
else:
    if best_name.startswith('xgb'):
        final_model = best_xgb
    else:
        final_model = lgbm_smote

# ========= 鎵撳嵃瀹屾暣璇勪及 =========
print(f"\n{'='*50}")
print(f"鏈€缁堟ā鍨? {best_name}")
print(f"鍑嗙‘鐜? {best_acc*100:.2f}%")
print(f"{'='*50}")

y_pred = final_model.predict(X_test_s)
report = classification_report(y_test, y_pred, target_names=['鏆磋穼', '骞崇ǔ', '鏆存定'])
print(report)

cm = confusion_matrix(y_test, y_pred)
print(f"Confusion Matrix:")
print(cm)

extreme_recall = (cm[0,0] + cm[-1,-1]) / (cm[0,:].sum() + cm[-1,:].sum() + 1e-10)
print(f"鏆存定+鏆磋穼鍚堝苟鍙洖鐜? {extreme_recall*100:.2f}%")

# ========= 淇濆瓨妯″瀷 =========
print(f"\n[{datetime.now():%H:%M:%S}] 淇濆瓨妯″瀷...")
model_type_str = 'xgboost' if best_name.startswith('xgb') else 'lightgbm'
model_path = 'trend_3class_model.json'

if model_type_str == 'xgboost':
    final_model.save_model(model_path)
else:
    final_model.booster_.save_model(model_path)

meta = {
    'model_type': model_type_str,
    'feature_columns': feature_columns,
    'label_names': label_names,
    'label_thresholds': {'q20': float(q20), 'q80': float(q80)},
    'keyword_encoding': {str(k): int(v) for k, v in keyword_map.items()},
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
    'best_model_name': best_name,
    'ensemble_acc': float(ensemble_acc),
    'trained_at': datetime.now().isoformat(),
}
meta_path = 'trend_3class_model_meta.json'
with open(meta_path, 'w', encoding='utf-8') as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

print(f"妯″瀷淇濆瓨: {model_path}")
print(f"鍏冩暟鎹? {meta_path}")

# ========= 缁撴灉鎽樿 =========
print(f"\n{'='*60}")
print(f"  3鍒嗙被妯″瀷璁粌瀹屾垚")
print(f"  鍑嗙‘鐜? {best_acc*100:.2f}%  {'鉁?>=82%' if best_acc >= TARGET_ACC else '鉁?<82%'}")
print(f"  鏋佺鍙洖鐜? {extreme_recall*100:.2f}%")
print(f"  鏈€浣虫ā鍨? {best_name}")
print(f"  Ensemble Acc: {ensemble_acc*100:.2f}%")
print(f"{'='*60}")
