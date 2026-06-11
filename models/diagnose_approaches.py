#!/usr/bin/env python3
"""
璇婃柇锛氬皾璇曞绉嶅缓妯＄瓥鐣ワ紝鎵惧嚭鏈€浣虫柟娉?鍏抽敭淇敼: keyword褰掍竴鍖?+ 3绫?+ 鍥炲綊娣峰悎
"""
import configparser
import logging
import os
import warnings

import numpy as np
import pandas as pd
import pymysql
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.preprocessing import RobustScaler
from xgboost import XGBClassifier, XGBRegressor

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)


def get_connection(config):
    return pymysql.connect(
        host=config.get('database', 'host'),
        port=config.getint('database', 'port'),
        user=config.get('database', 'user'),
        password=config.get('database', 'password'),
        database=config.get('database', 'database'),
        charset='utf8mb4',
        connect_timeout=10, read_timeout=600, write_timeout=600,
    )


def load_data(conn):
    sql = "SELECT * FROM standardized_data WHERE publish_time >= '2023-01-01' ORDER BY keyword, publish_time"
    df = pd.read_sql(sql, conn)
    logger.info(f"鍏?{len(df)} 鏉¤褰?)
    return df


def feature_engineering(df):
    logger.info("鐗瑰緛宸ョ▼...")
    df['publish_time'] = pd.to_datetime(df['publish_time'])
    df['window_start'] = df['publish_time'].dt.floor('6H')

    agg = df.groupby(['keyword', 'window_start']).agg({
        'hot_score': ['sum', 'mean', 'max', 'std'],
        'like_count': 'sum', 'comment_count': 'sum', 'view_count': 'sum',
        'sentiment_score': 'mean', 'id': 'count',
    }).reset_index()
    agg.columns = [
        'keyword', 'window_start', 'total_hot', 'mean_hot', 'max_hot', 'std_hot',
        'total_like', 'total_comment', 'total_view',
        'avg_sentiment', 'count',
    ]
    agg = agg.sort_values(['keyword', 'window_start']).reset_index(drop=True)

    # ===== keyword 褰掍竴鍖栫壒寰?=====
    # 姣忎釜keyword鐨?total_hot 鍧囧€煎拰鏍囧噯宸?    keyword_stats = agg.groupby('keyword').agg(
        kw_mean_hot=('total_hot', 'mean'),
        kw_std_hot=('total_hot', 'std'),
        kw_mean_count=('count', 'mean'),
    ).reset_index()
    keyword_stats['kw_std_hot'] = keyword_stats['kw_std_hot'].replace(0, 1)
    agg = agg.merge(keyword_stats, on='keyword')

    # z-score 褰掍竴鍖栫殑 total_hot
    agg['total_hot_z'] = (agg['total_hot'] - agg['kw_mean_hot']) / agg['kw_std_hot']
    agg['total_hot_pct_of_mean'] = agg['total_hot'] / (agg['kw_mean_hot'] + 1e-6)

    # 婊炲悗鐗瑰緛
    for i in [1, 2, 3, 6]:
        agg[f'lag_{i}_total_hot'] = agg.groupby('keyword')['total_hot'].shift(i)
        agg[f'lag_{i}_count'] = agg.groupby('keyword')['count'].shift(i)
        agg[f'lag_{i}_total_hot_z'] = agg.groupby('keyword')['total_hot_z'].shift(i)

    # 鍙樺寲鐜?    agg['hot_change_rate'] = (
        (agg['total_hot'] - agg['lag_1_total_hot']) / (agg['lag_1_total_hot'] + 1e-6)
    )
    agg['count_change_rate'] = (
        (agg['count'] - agg['lag_1_count']) / (agg['lag_1_count'] + 1e-6)
    )

    # 瓒嬪娍鏂瑰悜 (杩囧幓3涓獥鍙ｇ殑鏂瑰悜璁℃暟)
    agg['trend_up_count'] = (
        ((agg['total_hot'] > agg['lag_1_total_hot']).astype(int)) +
        ((agg['lag_1_total_hot'] > agg['lag_2_total_hot']).astype(int)) +
        ((agg['lag_2_total_hot'] > agg['lag_3_total_hot']).astype(int))
    )

    # 鐩爣
    agg['future_total_hot'] = agg.groupby('keyword')['total_hot'].shift(-1)
    agg['change_rate'] = (
        (agg['future_total_hot'] - agg['total_hot']) / (agg['total_hot'] + 1e-6)
    )
    agg = agg.dropna(subset=['future_total_hot'])

    # 鍘熷5鍒嗙被鏍囩
    agg['label_5'] = 2
    agg.loc[agg['change_rate'] > 1.0, 'label_5'] = 4
    agg.loc[(agg['change_rate'] > 0.1) & (agg['change_rate'] <= 1.0), 'label_5'] = 3
    agg.loc[(agg['change_rate'] < -0.1) & (agg['change_rate'] >= -0.5), 'label_5'] = 1
    agg.loc[agg['change_rate'] < -0.5, 'label_5'] = 0

    # 3绫绘柟鍚戞爣绛?(鍒嗕綅鏁板钩琛?
    q30 = agg['change_rate'].quantile(0.30)
    q70 = agg['change_rate'].quantile(0.70)
    agg['label_3'] = 1  # 骞崇ǔ
    agg.loc[agg['change_rate'] > q70, 'label_3'] = 2  # 涓婂崌
    agg.loc[agg['change_rate'] < q30, 'label_3'] = 0  # 涓嬮檷

    # 3绫绘椿鍔ㄦ按骞虫爣绛?    hot_q33 = agg['total_hot'].quantile(0.33)
    hot_q67 = agg['total_hot'].quantile(0.67)
    agg['label_hml'] = 1
    agg.loc[agg['future_total_hot'] <= hot_q33, 'label_hml'] = 0
    agg.loc[agg['future_total_hot'] >= hot_q67, 'label_hml'] = 2

    # log 鍙樻崲鐗瑰緛
    agg['log_total_hot'] = np.log1p(agg['total_hot'])
    agg['log_future_total_hot'] = np.log1p(agg['future_total_hot'])

    # 鏃堕棿鐗瑰緛
    agg['hour'] = agg['window_start'].dt.hour
    agg['day_of_week'] = agg['window_start'].dt.dayofweek
    agg['is_weekend'] = (agg['day_of_week'] >= 5).astype(int)

    # 濉厖
    agg = agg.fillna(0).replace([np.inf, -np.inf], 0)

    logger.info(f"鐗瑰緛瀹屾垚: {len(agg)} 鏍锋湰")
    return agg


def evaluate_model(model, X_test, y_test, name="妯″瀷"):
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    cm = confusion_matrix(y_test, y_pred)
    logger.info(f"{name}: acc={acc:.4f}")
    logger.info(f"娣锋穯鐭╅樀:\n{cm}")
    return acc


def main():
    config = configparser.ConfigParser()
    config_path = 'config.ini'
    if os.path.exists(config_path):
        config.read(config_path, encoding='utf-8')
    else:
        config['database'] = {'host': '<SERVER_IP>', 'port': '3306',
                              'user': 'spark', 'password': '123456', 'database': 'standardized_data'}

    conn = get_connection(config)
    try:
        df = load_data(conn)
        agg = feature_engineering(df)

        # 鐗瑰緛鍒?        feature_cols = [
            'total_hot', 'mean_hot', 'max_hot', 'std_hot', 'log_total_hot',
            'total_hot_z', 'total_hot_pct_of_mean',
            'total_like', 'total_comment', 'total_view',
            'avg_sentiment', 'count',
            'lag_1_total_hot', 'lag_2_total_hot', 'lag_3_total_hot', 'lag_6_total_hot',
            'lag_1_count', 'lag_2_count', 'lag_3_count', 'lag_6_count',
            'lag_1_total_hot_z', 'lag_2_total_hot_z', 'lag_3_total_hot_z', 'lag_6_total_hot_z',
            'hot_change_rate', 'count_change_rate',
            'trend_up_count',
            'hour', 'day_of_week', 'is_weekend',
            'kw_mean_hot', 'kw_std_hot', 'kw_mean_count',
        ]

        # 鏃堕棿鍒掑垎
        times = sorted(agg['window_start'].unique())
        n = len(times)
        train_cut = times[int(n * 0.7)]
        val_cut = times[int(n * 0.85)]

        train_df = agg[agg['window_start'] <= train_cut].copy()
        val_df = agg[(agg['window_start'] > train_cut) & (agg['window_start'] <= val_cut)].copy()
        test_df = agg[agg['window_start'] > val_cut].copy()

        logger.info(f"璁粌={len(train_df)}, 楠岃瘉={len(val_df)}, 娴嬭瘯={len(test_df)}")
        for name, df_set in [('璁粌', train_df), ('娴嬭瘯', test_df)]:
            for lbl in ['label_5', 'label_3', 'label_hml']:
                counts = df_set[lbl].value_counts().sort_index()
                dist = {k: f"{v/len(df_set)*100:.1f}%" for k, v in counts.items()}
                logger.info(f"  {name} {lbl}: {dist}")

        # 鍑嗗鏁版嵁
        X_train = train_df[feature_cols].values
        X_val = val_df[feature_cols].values
        X_test = test_df[feature_cols].values

        scaler = RobustScaler()
        X_train = scaler.fit_transform(X_train)
        X_val = scaler.transform(X_val)
        X_test = scaler.transform(X_test)

        results = {}

        # ===== 1. 鐩存帴5鍒嗙被 =====
        logger.info("\n--- 1. 鐩存帴5鍒嗙被 ---")
        m1 = XGBClassifier(
            objective='multi:softprob', num_class=5, eval_metric='mlogloss',
            max_depth=8, learning_rate=0.05, n_estimators=2000,
            subsample=0.8, colsample_bytree=0.8,
            reg_lambda=3.0, reg_alpha=1.0, min_child_weight=3,
            random_state=42, early_stopping_rounds=50,
        )
        m1.fit(X_train, train_df['label_5'].values, eval_set=[(X_val, val_df['label_5'].values)], verbose=0)
        results['5class'] = evaluate_model(m1, X_test, test_df['label_5'].values, "5鍒嗙被")

        # ===== 2. 鐩存帴3绫绘柟鍚?=====
        logger.info("\n--- 2. 3绫绘柟鍚?(鍒嗕綅鏁板钩琛? ---")
        m2 = XGBClassifier(
            objective='multi:softprob', num_class=3, eval_metric='mlogloss',
            max_depth=8, learning_rate=0.05, n_estimators=2000,
            subsample=0.8, colsample_bytree=0.8,
            random_state=42, early_stopping_rounds=50,
        )
        m2.fit(X_train, train_df['label_3'].values, eval_set=[(X_val, val_df['label_3'].values)], verbose=0)
        results['3class_dir'] = evaluate_model(m2, X_test, test_df['label_3'].values, "3绫绘柟鍚?)

        # 璇︾粏鎶ュ憡
        y_pred3 = m2.predict(X_test)
        logger.info("3绫绘柟鍚戣缁嗘姤鍛?")
        logger.info(classification_report(test_df['label_3'].values, y_pred3, target_names=['涓嬮檷', '骞崇ǔ', '涓婂崌']))

        # ===== 3. 3绫绘椿鍔ㄦ按骞?=====
        logger.info("\n--- 3. 3绫绘椿鍔ㄦ按骞?---")
        m3 = XGBClassifier(
            objective='multi:softprob', num_class=3, eval_metric='mlogloss',
            max_depth=8, learning_rate=0.05, n_estimators=2000,
            subsample=0.8, colsample_bytree=0.8,
            random_state=42, early_stopping_rounds=50,
        )
        m3.fit(X_train, train_df['label_hml'].values, eval_set=[(X_val, val_df['label_hml'].values)], verbose=0)
        results['3class_hml'] = evaluate_model(m3, X_test, test_df['label_hml'].values, "3绫绘椿鍔ㄦ按骞?)

        # ===== 4. 鍥炲綊棰勬祴 log_total_hot 鈫?鎺ㄥ3绫绘柟鍚?=====
        logger.info("\n--- 4. 鍥炲綊鈫?绫绘柟鍚?---")
        reg = XGBRegressor(
            objective='reg:squarederror', eval_metric='rmse',
            max_depth=8, learning_rate=0.05, n_estimators=2000,
            subsample=0.8, colsample_bytree=0.8,
            reg_lambda=3.0, reg_alpha=1.0,
            random_state=42, early_stopping_rounds=50,
        )
        reg.fit(X_train, train_df['log_future_total_hot'].values,
                eval_set=[(X_val, val_df['log_future_total_hot'].values)], verbose=0)

        pred_log_future = reg.predict(X_test)
        pred_future = np.expm1(pred_log_future)
        current_total = test_df['total_hot'].values
        implied_change = (pred_future - current_total) / (current_total + 1e-6)

        # 鐢ㄥ悓鏍风殑鍒嗕綅鏁伴槇鍊?        q30 = agg['change_rate'].quantile(0.30)
        q70 = agg['change_rate'].quantile(0.70)

        reg_pred = np.ones(len(implied_change), dtype=int)
        reg_pred[implied_change > q70] = 2
        reg_pred[implied_change < q30] = 0
        reg_acc = accuracy_score(test_df['label_3'].values, reg_pred)
        results['reg2dir'] = reg_acc
        logger.info(f"鍥炲綊鈫?绫绘柟鍚? {reg_acc:.4f}")

        # ===== 5. 鍥炲綊鈫抙ot_level (瀵规瘮actual hot_level) =====
        logger.info("\n--- 5. 鍥炲綊鈫掓椿鍔ㄦ按骞?---")
        hot_q33 = agg['total_hot'].quantile(0.33)
        hot_q67 = agg['total_hot'].quantile(0.67)
        reg_pred_hml = np.ones(len(pred_future), dtype=int)
        reg_pred_hml[pred_future <= hot_q33] = 0
        reg_pred_hml[pred_future >= hot_q67] = 2
        reg_hml_acc = accuracy_score(test_df['label_hml'].values, reg_pred_hml)
        results['reg2hml'] = reg_hml_acc
        logger.info(f"鍥炲綊鈫掓椿鍔ㄦ按骞? {reg_hml_acc:.4f}")

        # ===== 6. 鎸佷箙鎬?baseline (3绫绘柟鍚? =====
        logger.info("\n--- 6. 鎸佷箙鎬?baseline ---")
        # 褰撳墠绐楀彛鐨刢hange_rate 鈫?褰撳墠label 鈫?浣滀负涓嬩竴绐楀彛鐨勯娴?        current_labels = np.ones(len(test_df), dtype=int)
        current_change_rate = test_df['hot_change_rate'].values
        current_labels[current_change_rate > q70] = 2
        current_labels[current_change_rate < q30] = 0
        persistence_acc = accuracy_score(test_df['label_3'].values, current_labels)
        results['persistence'] = persistence_acc
        logger.info(f"鎸佷箙鎬?baseline: {persistence_acc:.4f}")

        # ===== 7. 澶氭暟绫?baseline =====
        most_common = train_df['label_3'].mode().values[0]
        majority_acc = (test_df['label_3'].values == most_common).mean()
        results['majority'] = majority_acc
        logger.info(f"澶氭暟绫?baseline: {majority_acc:.4f}")

        # ===== 鎬荤粨 =====
        logger.info("\n" + "=" * 50)
        logger.info("鎵€鏈夋柟娉曞姣?")
        for name, acc in sorted(results.items(), key=lambda x: -x[1]):
            logger.info(f"  {name}: {acc*100:.2f}%")

        # 淇濆瓨鏈€浣?绫绘ā鍨?        m2.save_model('trend_3class_model.json')

        return results
    finally:
        conn.close()


if __name__ == '__main__':
    main()
