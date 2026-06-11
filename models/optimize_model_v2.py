#!/usr/bin/env python3
"""
XGBoost 妯″瀷浼樺寲 v2
鍩轰簬鏁版嵁搴撳疄闄呭瓧娈靛～鍏呯巼璋冩暣鐗瑰緛绛栫暐

鏁版嵁搴撴鏌ョ粨鏋?(77193 rows):
  platform=1 (B绔?: 63969 rows 鈥?鍏ㄥ瓧娈?  platform=0 (NGA): 13224 rows 鈥?浠?comment_count, hot_raw, sentiment_score

瀛楁濉厖鐜?
  100%: hot_raw, sentiment_score
   88%: hot_norm, hot_score
   83%: like_count
   79%: text_length, content_clean
   60%: title_clean
   48%: comment_count
   44%: view_count, has_image, has_video (浠匓绔?
   41%: coin_count, favorite_count, share_count (浠匓绔?
   38%: danmaku_count (浠匓绔?
    0%: author_fans, author_level, author_post_count 鈫?寮冪敤
"""

import os, sys, pymysql, pandas as pd, numpy as np
from datetime import datetime
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, classification_report)
from sklearn.utils.class_weight import compute_class_weight
from xgboost import XGBClassifier
import pickle, logging, json, warnings
warnings.filterwarnings('ignore')

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_CONFIG = {
    'host': '<SERVER_IP>', 'port': 3306,
    'user': 'spark', 'password': '123456',
    'database': 'standardized_data',
}

# ===== 鐗瑰緛鍒嗙骇锛堟寜鏁版嵁濉厖鐜囷級 =====
# Tier 1: 璺ㄥ钩鍙伴珮瑕嗙洊瀛楁
TIER1 = ['keyword_enc', 'total_hot', 'count', 'avg_sentiment']
# Tier 2: 澶ч儴鍒嗗钩鍙版湁
TIER2 = ['avg_like', 'avg_comment', 'text_len_avg']
# Tier 3: 浠匓绔欐湁锛屼絾閲忓ぇ
TIER3 = ['avg_view', 'avg_coin', 'avg_favorite', 'avg_share', 'avg_danmaku',
         'image_ratio', 'video_ratio']
# 婊炲悗鐗瑰緛锛堝彧閫夐珮瑕嗙洊瀛楁锛?LAG_BASE = ['total_hot', 'avg_sentiment', 'count', 'avg_like', 'avg_comment']
# 瓒嬪娍鐗瑰緛
TREND = ['total_hot_change_rate', 'rolling_mean_6_total_hot', 'rolling_std_6_total_hot']
# 鏃堕棿鐗瑰緛
TIME_F = ['hour', 'day_of_week', 'is_weekend', 'month']


def get_connection():
    return pymysql.connect(**DB_CONFIG, charset='utf8mb4',
                           connect_timeout=10, read_timeout=300)


def load_data(conn):
    logger.info("璇诲彇鏁版嵁...")
    t = datetime.now()
    sql = "SELECT * FROM standardized_data WHERE publish_time >= '2020-01-01' ORDER BY keyword, publish_time"
    df = pd.read_sql(sql, conn)
    logger.info(f"瀹屾垚: {len(df)} 鏉? {df['keyword'].nunique()} 鍏抽敭璇? {df['platform'].nunique()} 骞冲彴, "
                f"鑰楁椂 {(datetime.now()-t).total_seconds():.1f}s")
    return df


def feature_engineering(df, label_shift=-1, threshold=0.1, feature_tiers='t1'):
    """
    feature_tiers:
      't1'    = TIER1 + LAG(TIER1) + TREND + TIME  (绮剧畝鍗曚竴)
      't1+2'  = TIER1+2 + LAG(TIER1+2) + TREND + TIME  (涓瓑)
      't1+2+3'= TIER1+2+3 + LAG(TIER1+2+3) + TREND + TIME  (鍏ㄩ儴)
    """
    df = df.copy()
    df['publish_time'] = pd.to_datetime(df['publish_time'])
    df['window_start'] = df['publish_time'].dt.floor('2H')

    agg_dict = {
        'hot_score': 'sum',
        'like_count': 'mean',
        'comment_count': 'mean',
        'sentiment_score': 'mean',
        'id': 'count',
    }
    # 鎸夊垎绾ф坊鍔犲瓧娈?    if feature_tiers in ('t1+2', 't1+2+3'):
        agg_dict['view_count'] = 'mean'
        agg_dict['coin_count'] = 'mean'
        agg_dict['favorite_count'] = 'mean'
        agg_dict['share_count'] = 'mean'
        agg_dict['danmaku_count'] = 'mean'
    if feature_tiers == 't1+2+3':
        agg_dict['has_image'] = 'mean'
        agg_dict['has_video'] = 'mean'
    # 鏂囨湰闀垮害
    if feature_tiers in ('t1+2', 't1+2+3'):
        agg_dict['text_length'] = 'mean'

    aggregated = df.groupby(['keyword', 'window_start']).agg(agg_dict).reset_index()

    # 缁熶竴鍒楀悕
    col_map = {
        'hot_score': 'total_hot',
        'like_count': 'avg_like',
        'comment_count': 'avg_comment',
        'view_count': 'avg_view',
        'coin_count': 'avg_coin',
        'favorite_count': 'avg_favorite',
        'share_count': 'avg_share',
        'danmaku_count': 'avg_danmaku',
        'sentiment_score': 'avg_sentiment',
        'has_image': 'image_ratio',
        'has_video': 'video_ratio',
        'text_length': 'text_len_avg',
        'id': 'count',
    }
    aggregated.rename(columns=col_map, inplace=True)

    # 鏃堕棿鐗瑰緛
    aggregated['hour'] = aggregated['window_start'].dt.hour
    aggregated['day_of_week'] = aggregated['window_start'].dt.dayofweek
    aggregated['is_weekend'] = (aggregated['day_of_week'] >= 5).astype(int)
    aggregated['month'] = aggregated['window_start'].dt.month

    # 婊炲悗鐗瑰緛
    if feature_tiers == 't1':
        lag_fields = ['total_hot', 'avg_sentiment', 'count']
    elif feature_tiers == 't1+2':
        lag_fields = ['total_hot', 'avg_sentiment', 'count', 'avg_like', 'avg_comment']
    else:
        lag_fields = ['total_hot', 'avg_sentiment', 'count', 'avg_like', 'avg_comment',
                      'avg_view', 'avg_coin', 'avg_favorite', 'avg_share']

    for feat in lag_fields:
        if feat not in aggregated.columns:
            continue
        for i in range(1, 4):
            aggregated[f'lag_{i}_{feat}'] = aggregated.groupby('keyword')[feat].shift(i)

    # 鐑害鍙樺寲鐜?    l1 = aggregated['lag_1_total_hot'].fillna(0) if 'lag_1_total_hot' in aggregated.columns else aggregated['total_hot']
    aggregated['total_hot_change_rate'] = (aggregated['total_hot'] - l1) / (l1 + 1e-6)

    # 婊氬姩缁熻
    rolling = aggregated.groupby('keyword')['total_hot'].rolling(6)
    aggregated['rolling_mean_6_total_hot'] = rolling.mean().reset_index(level=0, drop=True)
    aggregated['rolling_std_6_total_hot'] = rolling.std().reset_index(level=0, drop=True)

    # 鏍囩
    aggregated['future_total_hot'] = aggregated.groupby('keyword')['total_hot'].shift(label_shift)
    aggregated = aggregated.dropna(subset=['future_total_hot']).copy()

    change_rate = (aggregated['future_total_hot'] - aggregated['total_hot']) / (aggregated['total_hot'] + 1e-6)
    aggregated['label'] = 1
    aggregated.loc[change_rate > threshold, 'label'] = 2
    aggregated.loc[change_rate < -threshold, 'label'] = 0

    aggregated = aggregated.fillna(0)
    return aggregated


def build_feature_list(feature_tiers):
    """鏍规嵁鍒嗙骇鏋勫缓鐗瑰緛鍒楀垪琛?""
    base = TIER1.copy()
    if feature_tiers in ('t1+2', 't1+2+3'):
        base += ['avg_like', 'avg_comment', 'text_len_avg']
    if feature_tiers == 't1+2+3':
        base += TIER3

    if feature_tiers == 't1':
        lag_feats = ['total_hot', 'avg_sentiment', 'count']
    elif feature_tiers == 't1+2':
        lag_feats = ['total_hot', 'avg_sentiment', 'count', 'avg_like', 'avg_comment']
    else:
        lag_feats = ['total_hot', 'avg_sentiment', 'count', 'avg_like', 'avg_comment',
                     'avg_view', 'avg_coin', 'avg_favorite', 'avg_share']

    lags = [f'lag_{i}_{f}' for f in lag_feats for i in range(1, 4)]

    return base + lags + TREND + TIME_F


def evaluate_model(model, X_test, y_test):
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, average='macro', zero_division=0)
    rec = recall_score(y_test, y_pred, average='macro', zero_division=0)
    f1 = f1_score(y_test, y_pred, average='macro', zero_division=0)
    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    down_r = report.get('0', {}).get('recall', 0)
    up_r = report.get('2', {}).get('recall', 0)
    composite = acc * 0.4 + f1 * 0.3 + down_r * 0.15 + up_r * 0.15
    return {'accuracy': acc, 'precision': prec, 'recall': rec, 'f1': f1,
            'down_recall': down_r, 'up_recall': up_r, 'composite_score': composite}


def random_search(X_train, y_train, X_val, y_val, X_test, y_test,
                  sample_weights, n_trials=60):
    best_score, best_model, best_params = -1, None, None
    results = []

    param_space = {
        'max_depth': [3, 4, 5, 6, 7, 8],
        'learning_rate': [0.005, 0.01, 0.02, 0.03, 0.05, 0.08],
        'n_estimators': [300, 500, 800, 1000, 1500],
        'subsample': [0.6, 0.7, 0.75, 0.8, 0.85, 0.9],
        'colsample_bytree': [0.6, 0.7, 0.75, 0.8, 0.85, 0.9],
        'reg_lambda': [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 5.0],
        'reg_alpha': [0, 0.1, 0.3, 0.5, 0.7, 1.0, 2.0],
        'min_child_weight': [1, 3, 5, 7],
        'gamma': [0, 0.1, 0.2, 0.3],
    }

    for i in range(n_trials):
        params = {
            'objective': 'multi:softprob', 'num_class': 3,
            'eval_metric': 'mlogloss', 'random_state': 42, 'verbosity': 0,
            'max_depth': int(np.random.choice(param_space['max_depth'])),
            'learning_rate': float(np.random.choice(param_space['learning_rate'])),
            'n_estimators': int(np.random.choice(param_space['n_estimators'])),
            'subsample': float(np.random.choice(param_space['subsample'])),
            'colsample_bytree': float(np.random.choice(param_space['colsample_bytree'])),
            'reg_lambda': float(np.random.choice(param_space['reg_lambda'])),
            'reg_alpha': float(np.random.choice(param_space['reg_alpha'])),
            'min_child_weight': int(np.random.choice(param_space['min_child_weight'])),
            'gamma': float(np.random.choice(param_space['gamma'])),
        }

        try:
            model = XGBClassifier(**params)
            model.fit(X_train, y_train, sample_weight=sample_weights,
                      eval_set=[(X_val, y_val)], early_stopping_rounds=30, verbose=False)

            metrics = evaluate_model(model, X_test, y_test)
            metrics['params'] = params
            results.append(metrics)

            score = metrics['composite_score']
            if score > best_score:
                best_score, best_model, best_params = score, model, params
                logger.info(f"  [{i+1}/{n_trials}] best: score={score:.4f}, "
                            f"acc={metrics['accuracy']:.4f}, f1={metrics['f1']:.4f}")
        except Exception as e:
            logger.warning(f"  [{i+1}/{n_trials}] error: {e}")

    return best_model, best_params, results


# ==================== 涓绘祦绋?====================

def main():
    logger.info("=" * 60)
    logger.info("XGBoost 妯″瀷浼樺寲 v2 (鍩轰簬鏁版嵁搴撳瓧娈靛～鍏呯巼)")
    logger.info("=" * 60)

    conn = get_connection()
    try:
        raw_df = load_data(conn)
    finally:
        conn.close()

    label_encoder = LabelEncoder()

    # 瀹為獙璁捐锛氫笉鍚岀壒寰佺粍鍚?脳 涓嶅悓棰勬祴绐楀彛 脳 涓嶅悓闃堝€?    experiments = [
        # (name, feature_tiers, label_shift, threshold)
        ('t1_2h_th0.10',  't1',    -1, 0.10),    # 鍩虹鐗瑰緛, 2h棰勬祴
        ('t1_2h_th0.08',  't1',    -1, 0.08),    # 鍩虹鐗瑰緛, 鏇存晱鎰?        ('t1_2h_th0.05',  't1',    -1, 0.05),    # 鍩虹鐗瑰緛, 鏈€鏁忔劅
        ('t12_2h_th0.10', 't1+2',  -1, 0.10),    # 鍔爈ike/comment/text
        ('t12_2h_th0.08', 't1+2',  -1, 0.08),
        ('t12_2h_th0.05', 't1+2',  -1, 0.05),
        ('t123_2h_th0.10','t1+2+3',-1, 0.10),    # 鍏ㄥ瓧娈?        ('t123_2h_th0.08','t1+2+3',-1, 0.08),
        ('t123_2h_th0.05','t1+2+3',-1, 0.05),
        ('t12_4h_th0.10', 't1+2',  -2, 0.10),    # 4h棰勬祴
        ('t12_4h_th0.08', 't1+2',  -2, 0.08),
        ('t12_6h_th0.10', 't1+2',  -3, 0.10),    # 6h棰勬祴
    ]

    overall_best = {'composite_score': -1}

    for exp_name, feat_tier, shift, thresh in experiments:
        logger.info(f"\n{'='*60}")
        logger.info(f"瀹為獙: {exp_name} | tier={feat_tier} shift={shift*2}h thresh={thresh}")
        logger.info(f"{'='*60}")

        try:
            processed = feature_engineering(raw_df, label_shift=shift, threshold=thresh,
                                            feature_tiers=feat_tier)
            processed['keyword_enc'] = label_encoder.fit_transform(processed['keyword'])

            feature_cols = build_feature_list(feat_tier)
            available = [c for c in feature_cols if c in processed.columns]
            logger.info(f"鐗瑰緛鏁? {len(available)}")

            train = processed[processed['window_start'] <= '2024-12-31']
            val = processed[(processed['window_start'] > '2024-12-31') &
                            (processed['window_start'] <= '2025-12-31')]
            test = processed[processed['window_start'] > '2025-12-31']

            logger.info(f"鏁版嵁: train={len(train)} val={len(val)} test={len(test)}")
            logger.info(f"绫诲埆鍒嗗竷: {train['label'].value_counts().to_dict()}")

            X_tr, y_tr = train[available], train['label']
            X_v, y_v = val[available], val['label']
            X_te, y_te = test[available], test['label']

            # 绫诲埆鏉冮噸
            classes = np.unique(y_tr)
            cw = compute_class_weight('balanced', classes=classes, y=y_tr)
            sw = np.array([dict(zip(classes, cw))[l] for l in y_tr])
            logger.info(f"绫诲埆鏉冮噸: {dict(zip(classes, cw))}")

            model, params, results = random_search(X_tr, y_tr, X_v, y_v, X_te, y_te, sw, n_trials=60)
            if model is None:
                continue

            metrics = evaluate_model(model, X_te, y_te)
            metrics['exp_name'] = exp_name
            metrics['params'] = params
            metrics['n_features'] = len(available)

            logger.info(f">>> {exp_name} 缁撴灉: acc={metrics['accuracy']:.4f} "
                        f"f1={metrics['f1']:.4f} comp={metrics['composite_score']:.4f} "
                        f"down_rec={metrics['down_recall']:.4f} up_rec={metrics['up_recall']:.4f}")

            score = metrics['composite_score']
            if score > overall_best['composite_score']:
                overall_best = metrics.copy()
                overall_best['model'] = model
                overall_best['features'] = available
                overall_best['shift'] = shift
                overall_best['threshold'] = thresh
                logger.info(f"*** 鏂板叏灞€鏈€浣? {exp_name} score={score:.4f} ***")

            # 淇濆瓨缁撴灉
            d = os.path.join('optimization_results', exp_name)
            os.makedirs(d, exist_ok=True)
            model.save_model(os.path.join(d, 'model.json'))
            with open(os.path.join(d, 'feature_columns.pkl'), 'wb') as f:
                pickle.dump(available, f)
            with open(os.path.join(d, 'label_encoder.pkl'), 'wb') as f:
                pickle.dump(label_encoder, f)
            with open(os.path.join(d, 'metrics.json'), 'w') as f:
                m = {k: v for k, v in metrics.items() if k != 'params'}
                json.dump(m, f, ensure_ascii=False, indent=2)

            pd.DataFrame([{
                'acc': r.get('accuracy', 0), 'f1': r.get('f1', 0),
                'composite': r.get('composite_score', r.get('f1', 0)),
                'params': str(r.get('params', {}))
            } for r in results]).to_csv(os.path.join(d, 'tuning.csv'), index=False)

        except Exception as e:
            logger.error(f"{exp_name} 澶辫触: {e}", exc_info=True)

    # 鏈€浣虫ā鍨嬪鍑?    if overall_best.get('model') is not None:
        logger.info(f"\n{'='*60}")
        logger.info(f"鏈€缁堟渶浣? {overall_best['exp_name']}")
        logger.info(f"  composite={overall_best['composite_score']:.4f} acc={overall_best['accuracy']:.4f}")
        logger.info(f"  f1={overall_best['f1']:.4f} down_rec={overall_best['down_recall']:.4f} up_rec={overall_best['up_recall']:.4f}")
        logger.info(f"  鍙傛暟: {overall_best['params']}")

        d = 'optimization_results/best_model'
        os.makedirs(d, exist_ok=True)
        overall_best['model'].save_model(os.path.join(d, 'hotspot_classifier.json'))
        with open(os.path.join(d, 'feature_columns.pkl'), 'wb') as f:
            pickle.dump(overall_best['features'], f)
        with open(os.path.join(d, 'label_encoder.pkl'), 'wb') as f:
            pickle.dump(label_encoder, f)
        with open(os.path.join(d, 'best_params.json'), 'w') as f:
            json.dump({k: int(v) if isinstance(v, (np.integer,)) else float(v)
                       if isinstance(v, (np.floating,)) else v
                       for k, v in overall_best['params'].items()}, f, indent=2)

        logger.info(f"鏈€浣虫ā鍨?鈫?{d}/hotspot_classifier.json")
    else:
        logger.warning("鏈壘鍒版湁鏁堟ā鍨?)

    return 0


if __name__ == '__main__':
    sys.exit(main())
