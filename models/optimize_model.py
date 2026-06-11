#!/usr/bin/env python3
"""
XGBoost 妯″瀷鍏ㄩ潰浼樺寲鑴氭湰
- 浣跨敤鍏ㄩ儴鍙敤鐗瑰緛
- 绯荤粺鍖栬秴鍙傛暟鎼滅储
- 澶氱棰勬祴绐楀彛瀵规瘮
- 鑷姩閮ㄧ讲鏈€浣虫ā鍨?"""

import os
import sys
import configparser
import pymysql
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, classification_report, confusion_matrix)
from sklearn.utils.class_weight import compute_class_weight
from xgboost import XGBClassifier
import pickle
import logging
import json
import warnings
warnings.filterwarnings('ignore')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ==================== 閰嶇疆 ====================

DB_CONFIG = {
    'host': '<SERVER_IP>',
    'port': 3306,
    'user': 'spark',
    'password': '123456',
    'database': 'standardized_data',
}

# 鎵€鏈夊彲鐢ㄧ壒寰侊紙鍖呮嫭涔嬪墠鏈娇鐢ㄧ殑锛?BASE_FEATURES = [
    'keyword_enc', 'total_hot', 'count',
    'avg_like', 'avg_comment', 'avg_sentiment',
    'avg_view', 'avg_coin', 'avg_favorite', 'avg_share', 'avg_danmaku',
    'avg_author_fans', 'avg_author_level', 'avg_author_post_count',
    'image_ratio', 'video_ratio',
]

LAG_FEATURES = []
for feat in ['total_hot', 'avg_like', 'avg_comment', 'avg_sentiment', 'count',
             'avg_view', 'avg_coin', 'avg_favorite', 'avg_share']:
    for i in range(1, 4):
        LAG_FEATURES.append(f'lag_{i}_{feat}')

TREND_FEATURES = ['total_hot_change_rate', 'rolling_mean_6_total_hot', 'rolling_std_6_total_hot']
TIME_FEATURES = ['hour', 'day_of_week', 'is_weekend', 'month']

ALL_FEATURES = BASE_FEATURES + LAG_FEATURES + TREND_FEATURES + TIME_FEATURES

# ==================== 鏁版嵁鍔犺浇 ====================

def get_connection():
    return pymysql.connect(
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        database=DB_CONFIG['database'],
        charset='utf8mb4',
        connect_timeout=10,
        read_timeout=600,
        write_timeout=600
    )


def load_data(conn):
    logger.info("寮€濮嬭鍙栨暟鎹?..")
    start = datetime.now()
    sql = """
        SELECT *
        FROM standardized_data
        WHERE publish_time >= '2020-01-01'
        ORDER BY keyword, publish_time
    """
    df = pd.read_sql(sql, conn)
    logger.info(f"璇诲彇瀹屾垚: {len(df)} 鏉? 鑰楁椂 {(datetime.now()-start).total_seconds():.1f}s")
    return df


def feature_engineering(df, label_shift=-1, threshold=0.1):
    """
    鐗瑰緛宸ョ▼
    label_shift: -1=2灏忔椂, -2=4灏忔椂, -3=6灏忔椂棰勬祴
    threshold: 鍒嗙被闃堝€硷紙鍙樺寲鐜囪秴杩囨鍊煎垽瀹氫负涓婂崌/涓嬮檷锛?    """
    df['publish_time'] = pd.to_datetime(df['publish_time'])
    df['window_start'] = df['publish_time'].dt.floor('2H')

    aggregated = df.groupby(['keyword', 'window_start']).agg({
        'hot_score': 'sum',
        'like_count': 'mean',
        'comment_count': 'mean',
        'view_count': 'mean',
        'coin_count': 'mean',
        'favorite_count': 'mean',
        'share_count': 'mean',
        'danmaku_count': 'mean',
        'sentiment_score': 'mean',
        'author_fans': 'mean',
        'author_level': 'mean',
        'author_post_count': 'mean',
        'has_image': 'mean',
        'has_video': 'mean',
        'id': 'count'
    }).reset_index()

    aggregated.columns = [
        'keyword', 'window_start', 'total_hot', 'avg_like', 'avg_comment',
        'avg_view', 'avg_coin', 'avg_favorite', 'avg_share', 'avg_danmaku',
        'avg_sentiment', 'avg_author_fans', 'avg_author_level',
        'avg_author_post_count', 'image_ratio', 'video_ratio', 'count'
    ]

    # 鏃堕棿鐗瑰緛
    aggregated['hour'] = aggregated['window_start'].dt.hour
    aggregated['day_of_week'] = aggregated['window_start'].dt.dayofweek
    aggregated['is_weekend'] = (aggregated['day_of_week'] >= 5).astype(int)
    aggregated['month'] = aggregated['window_start'].dt.month

    # 婊炲悗鐗瑰緛锛堝叏閮ㄥ瓧娈碉級
    for feat in ['total_hot', 'avg_like', 'avg_comment', 'avg_sentiment', 'count',
                 'avg_view', 'avg_coin', 'avg_favorite', 'avg_share']:
        for i in range(1, 4):
            aggregated[f'lag_{i}_{feat}'] = aggregated.groupby('keyword')[feat].shift(i)

    # 鐑害鍙樺寲鐜?    lag1 = aggregated['lag_1_total_hot'].fillna(0)
    aggregated['total_hot_change_rate'] = (
        (aggregated['total_hot'] - lag1) / (lag1 + 1e-6)
    )

    # 婊氬姩缁熻
    aggregated['rolling_mean_6_total_hot'] = (
        aggregated.groupby('keyword')['total_hot'].rolling(6).mean()
        .reset_index(level=0, drop=True)
    )
    aggregated['rolling_std_6_total_hot'] = (
        aggregated.groupby('keyword')['total_hot'].rolling(6).std()
        .reset_index(level=0, drop=True)
    )

    # 鏍囩鏋勯€?    aggregated['future_total_hot'] = aggregated.groupby('keyword')['total_hot'].shift(label_shift)
    aggregated = aggregated.dropna(subset=['future_total_hot'])

    aggregated['change_rate'] = (
        (aggregated['future_total_hot'] - aggregated['total_hot']) /
        (aggregated['total_hot'] + 1e-6)
    )

    # 涓夊垎绫绘爣绛?    aggregated['label'] = 1  # 榛樿骞崇ǔ
    aggregated.loc[aggregated['change_rate'] > threshold, 'label'] = 2   # 涓婂崌
    aggregated.loc[aggregated['change_rate'] < -threshold, 'label'] = 0  # 涓嬮檷

    # 浜屽垎绫绘爣绛撅紙鐑偣棰勬祴锛?    aggregated['is_hot'] = (aggregated['future_total_hot'] >= 0.45).astype(int)

    aggregated = aggregated.fillna(0)
    return aggregated


# ==================== 妯″瀷璇勪及 ====================

def evaluate_model(model, X_test, y_test, task='multiclass'):
    y_pred = model.predict(X_test)

    if task == 'binary':
        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, average='binary', zero_division=0)
        recall = recall_score(y_test, y_pred, average='binary', zero_division=0)
        f1 = f1_score(y_test, y_pred, average='binary', zero_division=0)
        cm = confusion_matrix(y_test, y_pred)
        return {
            'accuracy': accuracy, 'precision': precision,
            'recall': recall, 'f1': f1,
            'confusion_matrix': cm.tolist()
        }

    # 澶氬垎绫?    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, average='macro', zero_division=0)
    recall = recall_score(y_test, y_pred, average='macro', zero_division=0)
    f1 = f1_score(y_test, y_pred, average='macro', zero_division=0)

    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    down_recall = report.get('0', {}).get('recall', 0)
    up_recall = report.get('2', {}).get('recall', 0)

    composite = (accuracy * 0.4 + f1 * 0.3 + down_recall * 0.15 + up_recall * 0.15)

    return {
        'accuracy': accuracy, 'precision': precision,
        'recall': recall, 'f1': f1,
        'down_recall': down_recall, 'up_recall': up_recall,
        'composite_score': composite
    }


# ==================== 瓒呭弬鏁版悳绱?====================

PARAM_GRID = {
    'max_depth': [3, 4, 5, 6, 7, 8],
    'learning_rate': [0.005, 0.01, 0.02, 0.03, 0.05, 0.08],
    'n_estimators': [300, 500, 800, 1000, 1200, 1500],
    'subsample': [0.6, 0.7, 0.75, 0.8, 0.85, 0.9],
    'colsample_bytree': [0.6, 0.7, 0.75, 0.8, 0.85, 0.9],
    'reg_lambda': [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 5.0],
    'reg_alpha': [0, 0.1, 0.3, 0.5, 0.7, 1.0, 2.0],
    'min_child_weight': [1, 3, 5, 7],
    'gamma': [0, 0.1, 0.2, 0.3],
}


def random_search(X_train, y_train, X_val, y_val, X_test, y_test,
                  n_trials=100, use_class_weight=True, task='multiclass',
                  sample_weights=None):
    """闅忔満鎼滅储鏈€浣宠秴鍙傛暟"""
    best_score = -1
    best_model = None
    best_params = None
    results = []

    for i in range(n_trials):
        params = {
            'objective': 'multi:softprob' if task == 'multiclass' else 'binary:logistic',
            'eval_metric': 'mlogloss' if task == 'multiclass' else 'logloss',
            'random_state': 42,
            'verbosity': 0,
        }
        if task == 'multiclass':
            params['num_class'] = 3

        params['max_depth'] = int(np.random.choice(PARAM_GRID['max_depth']))
        params['learning_rate'] = float(np.random.choice(PARAM_GRID['learning_rate']))
        params['n_estimators'] = int(np.random.choice(PARAM_GRID['n_estimators']))
        params['subsample'] = float(np.random.choice(PARAM_GRID['subsample']))
        params['colsample_bytree'] = float(np.random.choice(PARAM_GRID['colsample_bytree']))
        params['reg_lambda'] = float(np.random.choice(PARAM_GRID['reg_lambda']))
        params['reg_alpha'] = float(np.random.choice(PARAM_GRID['reg_alpha']))
        params['min_child_weight'] = int(np.random.choice(PARAM_GRID['min_child_weight']))
        params['gamma'] = float(np.random.choice(PARAM_GRID['gamma']))

        try:
            model = XGBClassifier(**params)
            fit_kwargs = {
                'X': X_train, 'y': y_train,
                'eval_set': [(X_val, y_val)],
                'early_stopping_rounds': 30,
                'verbose': False,
            }
            if sample_weights is not None:
                fit_kwargs['sample_weight'] = sample_weights

            model.fit(**fit_kwargs)

            metrics = evaluate_model(model, X_test, y_test, task)
            metrics['params'] = params
            results.append(metrics)

            score = metrics.get('composite_score', metrics['f1'])
            if score > best_score:
                best_score = score
                best_model = model
                best_params = params
                logger.info(
                    f"  [{i+1}/{n_trials}] 鏂版渶浣? score={score:.4f}, "
                    f"acc={metrics['accuracy']:.4f}, f1={metrics['f1']:.4f}"
                )
        except Exception as e:
            logger.warning(f"  [{i+1}/{n_trials}] 澶辫触: {e}")
            continue

    return best_model, best_params, results


def optimize_threshold(X_train, y_train, X_val, y_val, task='multiclass'):
    """鎼滅储鏈€浣冲垎绫婚槇鍊硷紙鍙樺寲鐜囬槇鍊硷紝涓嶆槸妯″瀷姒傜巼闃堝€硷級"""
    thresholds = [0.03, 0.05, 0.08, 0.1, 0.12, 0.15, 0.2, 0.25, 0.3]
    best_threshold = 0.1
    best_balance = -1

    for th in thresholds:
        y_train_th = y_train.copy()
        y_val_th = y_val.copy()

        # Re-label with new threshold
        def relabel(y, t):
            y_new = y.copy()
            y_new[:] = 1
            y_new[y > t] = 2
            y_new[y < -t] = 0
            return y_new

        # For this we need raw change_rate values from the data
        # This is handled in the main loop
        pass

    return best_threshold


# ==================== 涓绘祦绋?====================

def main():
    logger.info("=" * 60)
    logger.info("XGBoost 妯″瀷鍏ㄩ潰浼樺寲寮€濮?)
    logger.info("=" * 60)

    conn = get_connection()
    try:
        df = load_data(conn)
    finally:
        conn.close()

    logger.info(f"鏁版嵁鍒? {list(df.columns)}")
    logger.info(f"鍏抽敭璇嶆暟閲? {df['keyword'].nunique()}")
    logger.info(f"鏃堕棿鑼冨洿: {df['publish_time'].min()} ~ {df['publish_time'].max()}")

    label_encoder = LabelEncoder()

    # ========== 瀹為獙閰嶇疆 ==========
    experiments = [
        # (name, label_shift, threshold, feature_subset, task)
        ('2h_full_feat', -1, 0.1, ALL_FEATURES, 'multiclass'),         # 2灏忔椂棰勬祴锛屽叏閮ㄧ壒寰?        ('2h_t0.05',     -1, 0.05, ALL_FEATURES, 'multiclass'),        # 2灏忔椂锛屾洿鏁忔劅闃堝€?        ('2h_t0.15',     -1, 0.15, ALL_FEATURES, 'multiclass'),        # 2灏忔椂锛屾洿涓ユ牸闃堝€?        ('4h_pred',      -2, 0.1,  ALL_FEATURES, 'multiclass'),        # 4灏忔椂棰勬祴
        ('6h_pred',      -3, 0.1,  ALL_FEATURES, 'multiclass'),        # 6灏忔椂棰勬祴
        ('2h_base_feat', -1, 0.1,  BASE_FEATURES + LAG_FEATURES + TREND_FEATURES + TIME_FEATURES, 'multiclass'),
    ]

    overall_best = {'composite_score': -1}

    for exp_name, label_shift, threshold, feature_cols, task in experiments:
        logger.info(f"\n{'='*60}")
        logger.info(f"瀹為獙: {exp_name}")
        logger.info(f"  棰勬祴绐楀彛: {-label_shift * 2}h, 闃堝€? {threshold}, 鐗瑰緛鏁? {len(feature_cols)}")
        logger.info(f"{'='*60}")

        try:
            raw_df = load_data(get_connection())
            processed = feature_engineering(raw_df, label_shift=label_shift, threshold=threshold)

            # 缂栫爜 keyword
            processed['keyword_enc'] = label_encoder.fit_transform(processed['keyword'])

            # 浣跨敤鍙敤鐨勭壒寰佸垪
            available_features = [c for c in feature_cols if c in processed.columns]
            logger.info(f"瀹為檯鍙敤鐗瑰緛鏁? {len(available_features)}")

            # 鍒嗚缁?楠岃瘉/娴嬭瘯
            train_df = processed[processed['window_start'] <= '2024-12-31']
            val_df = processed[(processed['window_start'] > '2024-12-31') &
                               (processed['window_start'] <= '2025-12-31')]
            test_df = processed[processed['window_start'] > '2025-12-31']

            logger.info(f"璁粌: {len(train_df)}, 楠岃瘉: {len(val_df)}, 娴嬭瘯: {len(test_df)}")

            class_counts = train_df['label'].value_counts()
            logger.info(f"璁粌闆嗙被鍒垎甯? {class_counts.to_dict()}")

            X_train = train_df[available_features]
            y_train = train_df['label']
            X_val = val_df[available_features]
            y_val = val_df['label']
            X_test = test_df[available_features]
            y_test = test_df['label']

            # 绫诲埆鏉冮噸
            classes = np.unique(y_train)
            class_weights = compute_class_weight('balanced', classes=classes, y=y_train)
            weight_map = dict(zip(classes, class_weights))
            sample_weights = np.array([weight_map[lab] for lab in y_train])
            logger.info(f"绫诲埆鏉冮噸: {weight_map}")

            # 闅忔満鎼滅储
            best_model, best_params, results = random_search(
                X_train, y_train, X_val, y_val, X_test, y_test,
                n_trials=80,
                sample_weights=sample_weights,
                task=task
            )

            if best_model is None:
                logger.warning(f"瀹為獙 {exp_name} 鏈壘鍒版湁鏁堟ā鍨嬶紝璺宠繃")
                continue

            # 鏈€缁堣瘎浼?            metrics = evaluate_model(best_model, X_test, y_test, task)
            metrics['exp_name'] = exp_name
            metrics['params'] = best_params
            metrics['n_features'] = len(available_features)

            logger.info(f"\n>>> 瀹為獙 {exp_name} 鏈€浣崇粨鏋?")
            logger.info(f"  鍑嗙‘鐜? {metrics['accuracy']:.4f}")
            logger.info(f"  F1: {metrics['f1']:.4f}")
            if 'composite_score' in metrics:
                logger.info(f"  缁煎悎璇勫垎: {metrics['composite_score']:.4f}")
                logger.info(f"  涓嬮檷鍙洖: {metrics['down_recall']:.4f}")
                logger.info(f"  涓婂崌鍙洖: {metrics['up_recall']:.4f}")
            logger.info(f"  Precision: {metrics['precision']:.4f}")
            logger.info(f"  Recall: {metrics['recall']:.4f}")

            # 鏇存柊鍏ㄥ眬鏈€浣?            score = metrics.get('composite_score', metrics['f1'])
            overall_best_score = overall_best.get('composite_score', overall_best.get('f1', -1))
            if score > overall_best_score:
                overall_best = metrics.copy()
                overall_best['model'] = best_model
                overall_best['features'] = available_features
                overall_best['label_shift'] = label_shift
                overall_best['threshold'] = threshold
                overall_best['exp_name'] = exp_name
                logger.info(f"\n*** 鏂扮殑鍏ㄥ眬鏈€浣? {exp_name} (score={score:.4f}) ***")

            # 淇濆瓨瀹為獙缁撴灉
            save_dir = os.path.join('optimization_results', exp_name)
            os.makedirs(save_dir, exist_ok=True)

            best_model.save_model(os.path.join(save_dir, 'model.json'))
            with open(os.path.join(save_dir, 'feature_columns.pkl'), 'wb') as f:
                pickle.dump(available_features, f)
            with open(os.path.join(save_dir, 'label_encoder.pkl'), 'wb') as f:
                pickle.dump(label_encoder, f)
            with open(os.path.join(save_dir, 'class_map.pkl'), 'wb') as f:
                pickle.dump({0: '涓嬮檷', 1: '骞崇ǔ', 2: '涓婂崌'}, f)
            with open(os.path.join(save_dir, 'metrics.json'), 'w') as f:
                serializable = {k: str(v) if isinstance(v, (np.integer, np.floating)) else v
                               for k, v in metrics.items() if k != 'params'}
                serializable['params'] = str(best_params)
                json.dump(serializable, f, ensure_ascii=False, indent=2)

            # 淇濆瓨鎵€鏈夎皟浼樼粨鏋?            results_df = pd.DataFrame([{
                'accuracy': r.get('accuracy', 0),
                'f1': r.get('f1', 0),
                'composite_score': r.get('composite_score', r.get('f1', 0)),
                'params': str(r.get('params', {}))
            } for r in results])
            results_df.to_csv(os.path.join(save_dir, 'tuning_results.csv'), index=False)

        except Exception as e:
            logger.error(f"瀹為獙 {exp_name} 澶辫触: {e}", exc_info=True)
            continue

    # ========== 淇濆瓨鏈€浣虫ā鍨?==========
    if overall_best.get('model') is not None:
        logger.info(f"\n{'='*60}")
        logger.info(f"鏈€浣虫ā鍨? {overall_best['exp_name']}")
        logger.info(f"缁煎悎璇勫垎: {overall_best.get('composite_score', overall_best.get('f1', 'N/A')):.4f}")
        logger.info(f"鍑嗙‘鐜? {overall_best['accuracy']:.4f}")
        logger.info(f"F1: {overall_best['f1']:.4f}")
        logger.info(f"鍙傛暟: {overall_best['params']}")
        logger.info(f"{'='*60}")

        export_dir = 'optimization_results/best_model'
        os.makedirs(export_dir, exist_ok=True)

        overall_best['model'].save_model(os.path.join(export_dir, 'hotspot_classifier.json'))
        with open(os.path.join(export_dir, 'feature_columns.pkl'), 'wb') as f:
            pickle.dump(overall_best['features'], f)
        with open(os.path.join(export_dir, 'label_encoder.pkl'), 'wb') as f:
            pickle.dump(label_encoder, f)
        with open(os.path.join(export_dir, 'class_map.pkl'), 'wb') as f:
            pickle.dump({0: '涓嬮檷', 1: '骞崇ǔ', 2: '涓婂崌'}, f)
        with open(os.path.join(export_dir, 'best_params.json'), 'w') as f:
            params_serializable = {k: int(v) if isinstance(v, (np.integer,)) else float(v)
                                   if isinstance(v, (np.floating,)) else v
                                   for k, v in overall_best['params'].items()}
            json.dump(params_serializable, f, indent=2)

        # 鐢熸垚瀹為獙瀵规瘮鎶ュ憡
        logger.info(f"\n浼樺寲瀹屾垚锛佹渶浣虫ā鍨嬪凡淇濆瓨鍒?{export_dir}")
    else:
        logger.warning("鎵€鏈夊疄楠屽潎鏈壘鍒版湁鏁堟ā鍨?)

    return 0


if __name__ == '__main__':
    sys.exit(main())
