#!/usr/bin/env python3
"""
瓒嬪娍棰勬祴鏈嶅姟 (XGBoost 5鍒嗙被 + 鍥炲綊)
鍔犺浇璁粌濂界殑妯″瀷锛屼负缁欏畾 keyword 棰勬祴鏈潵6灏忔椂瓒嬪娍

API:
  GET /api/predict/trend?keyword=鐜嬭€呰崳鑰€
  GET /health

杩斿洖:
  {
    "keyword": "鐜嬭€呰崳鑰€",
    "trend_code": 4,        // 0=鏆磋穼 1=涓嬮檷 2=骞崇ǔ 3=涓婂崌 4=鏆存定
    "trend_label": "鏆存定",
    "confidence": 0.85,     // 缃俊搴?    "predicted_hot": 0.75,  // 棰勬祴鐨勪笅涓獥鍙ｇ儹搴?    "current_hot": 0.32,    // 褰撳墠绐楀彛鐑害
    "change_rate": 1.34     // 棰勬祴鍙樺寲鐜?  }
"""
import json
import logging
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pymysql
from flask import Flask, jsonify, request
from xgboost import XGBClassifier, XGBRegressor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Database configuration
DB_HOST = os.getenv("DB_HOST", "<SERVER_IP>")
DB_USER = os.getenv("DB_USER", "spark")
DB_PASSWORD = os.getenv("DB_PASSWORD", "your_db_password")
DB_NAME = os.getenv("DB_NAME", "standardized_data")

# ===== 妯″瀷璺緞 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "..", "..", "model_training")
CLS_MODEL_PATH = os.path.join(MODEL_DIR, "trend_5class_model.json")
META_PATH = os.path.join(MODEL_DIR, "trend_5class_model_meta.json")

# 鍏ㄥ眬
_cls_model = None
_meta = None
_label_map = {0: "鏆磋穼", 1: "涓嬮檷", 2: "骞崇ǔ", 3: "涓婂崌", 4: "鏆存定"}

# 缃俊搴﹂槇鍊硷紙浣垮噯纭巼杈惧埌80%锛?CONFIDENCE_THRESHOLD = 0.82


def get_db():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, charset="utf8mb4",
        connect_timeout=5,
    )


def load_models():
    global _cls_model, _meta
    if _cls_model is not None:
        return

    logger.info("鍔犺浇鍒嗙被妯″瀷...")
    _cls_model = XGBClassifier()
    _cls_model.load_model(CLS_MODEL_PATH)

    logger.info("鍔犺浇鍏冩暟鎹?..")
    with open(META_PATH, "r", encoding="utf-8") as f:
        _meta = json.load(f)

    logger.info(f"妯″瀷鍔犺浇瀹屾垚锛岀壒寰佹暟: {len(_meta['feature_columns'])}")


def build_features(conn, keyword):
    """
    涓?keyword 鏋勫缓鏈€鏂扮殑鐗瑰緛鍚戦噺
    鏌ヨ鍘嗗彶鏁版嵁 鈫?6H鑱氬悎 鈫?璁＄畻鐗瑰緛 鈫?杩斿洖鐗瑰緛鐭╅樀 (1琛?
    """
    # 鑾峰彇鏈€杩?7 澶╂暟鎹?    sql = """
        SELECT hot_score, like_count, comment_count, view_count,
               coin_count, favorite_count, share_count,
               sentiment_score, publish_time
        FROM standardized_data
        WHERE keyword = %s AND publish_time >= NOW() - INTERVAL 3 DAY
        ORDER BY publish_time
    """
    df = pd.read_sql(sql, conn, params=(keyword,))
    if len(df) < 10:
        logger.warning(f"{keyword}: 鏁版嵁涓嶈冻 ({len(df)}琛?")
        return None

    # 6H 鑱氬悎
    df['publish_time'] = pd.to_datetime(df['publish_time'])
    df['window_start'] = df['publish_time'].dt.floor('6H')

    agg = df.groupby('window_start').agg({
        'hot_score': ['sum', 'mean', 'max'],
        'like_count': 'sum', 'comment_count': 'sum', 'view_count': 'sum',
        'coin_count': 'sum', 'favorite_count': 'sum', 'share_count': 'sum',
        'sentiment_score': 'mean',
    }).reset_index()
    agg.columns = [
        'window_start', 'total_hot', 'mean_hot', 'max_hot',
        'total_like', 'total_comment', 'total_view',
        'total_coin', 'total_favorite', 'total_share',
        'avg_sentiment',
    ]
    agg = agg.sort_values('window_start').reset_index(drop=True)

    # 蹇呴』鏈?>= 7 涓獥鍙?    if len(agg) < 7:
        logger.warning(f"{keyword}: 绐楀彛涓嶈冻 ({len(agg)}涓?")
        return None

    # 璁＄畻 count (杩戜技)
    agg['count'] = 1  # 姣忎釜绐楀彛鑷冲皯鏈?鏉?
    # 鏃堕棿鐗瑰緛
    agg['hour'] = agg['window_start'].dt.hour
    agg['day_of_week'] = agg['window_start'].dt.dayofweek
    agg['is_weekend'] = (agg['day_of_week'] >= 5).astype(int)

    # 婊炲悗鐗瑰緛
    for i in [1, 2, 3, 6]:
        for feat in ['total_hot', 'count', 'total_comment']:
            if feat in agg.columns:
                agg[f'lag_{i}_{feat}'] = agg[feat].shift(i)

    # 鍙樺寲鐜?    agg['hot_change_rate'] = (agg['total_hot'] - agg['lag_1_total_hot']) / (agg['lag_1_total_hot'] + 1e-6)
    agg['count_change_rate'] = (agg['count'] - agg['lag_1_count']) / (agg['lag_1_count'] + 1e-6)

    # 瓒嬪娍鏂瑰悜
    agg['trend_up_count'] = (
        ((agg['total_hot'] > agg['lag_1_total_hot']).astype(int)) +
        ((agg['lag_1_total_hot'] > agg['lag_2_total_hot']).astype(int)) +
        ((agg['lag_2_total_hot'] > agg['lag_3_total_hot']).astype(int))
    )

    # 婊氬姩缁熻
    for w in [3, 6]:
        agg[f'rolling_mean_{w}_total_hot'] = agg['total_hot'].rolling(w).mean()
        agg[f'rolling_max_{w}_total_hot'] = agg['total_hot'].rolling(w).max()

    # log
    agg['log_total_hot'] = np.log1p(agg['total_hot'])

    # keyword 缂栫爜
    keyword_enc = _meta['label_encoding'].get(keyword, 0)
    agg['keyword_enc'] = keyword_enc

    # 鏈€鍚庝竴琛岋紙鏈€鏂扮獥鍙ｏ級
    latest = agg.iloc[-1:].copy()

    # 濉厖缂哄け
    feature_columns = _meta['feature_columns']
    for col in feature_columns:
        if col not in latest.columns:
            latest[col] = 0
    latest = latest.fillna(0).replace([np.inf, -np.inf], 0)

    # 纭繚鍒楅『搴忎竴鑷?    X = latest[feature_columns].values

    # 鑾峰彇褰撳墠鍜屾湭鏉ョ殑 hot
    current_hot = float(latest['total_hot'].values[0])
    # 濡傛灉鏈変笅涓€涓獥鍙ｇ殑瀹為檯鍊?    future_hot = None
    if len(agg) >= 8:
        future_hot = float(agg['total_hot'].iloc[-1])

    return X, current_hot, future_hot


@app.route('/api/predict/trend', methods=['GET'])
def predict():
    try:
        keyword = request.args.get('keyword', '')
        if not keyword:
            return jsonify({'code': 400, 'message': 'Missing keyword', 'data': None}), 400

        load_models()
        conn = get_db()

        try:
            result = build_features(conn, keyword)
            if result is None:
                return jsonify({'code': 200, 'message': 'success', 'data': {
                    'keyword': keyword,
                    'trend_code': 2, 'trend_label': '骞崇ǔ',
                    'confidence': 0.0, 'predicted_hot': 0,
                    'current_hot': 0, 'change_rate': 0,
                }})

            X, current_hot, _ = result
            y_proba = _cls_model.predict_proba(X)[0]
            y_pred = int(np.argmax(y_proba))
            confidence = float(np.max(y_proba))

            predicted_hot = current_hot
            if y_pred == 4:
                predicted_hot = current_hot * 2.0 if current_hot > 0 else 0.5
            elif y_pred == 3:
                predicted_hot = current_hot * 1.3
            elif y_pred == 1:
                predicted_hot = current_hot * 0.5
            elif y_pred == 0:
                predicted_hot = current_hot * 0.1

            change_rate = (predicted_hot - current_hot) / (current_hot + 1e-6)

            return jsonify({'code': 200, 'message': 'success', 'data': {
                'keyword': keyword,
                'trend_code': y_pred,
                'trend_label': _label_map[y_pred],
                'confidence': round(confidence, 4),
                'predicted_hot': round(predicted_hot, 4),
                'current_hot': round(current_hot, 4),
                'change_rate': round(change_rate, 4),
            }})
        finally:
            conn.close()

    except Exception as e:
        logger.error(f"棰勬祴鍑洪敊: {e}")
        return jsonify({'code': 500, 'message': str(e), 'data': None}), 500


@app.route('/api/predict/trend/batch', methods=['POST'])
def predict_batch():
    """鎵归噺棰勬祴"""
    try:
        data = request.get_json()
        if not data or 'keywords' not in data:
            return jsonify({'error': 'Missing keywords'}), 400

        keywords = data['keywords']
        load_models()
        conn = get_db()

        results = []
        try:
            for kw in keywords:
                result = build_features(conn, kw)
                if result is None:
                    results.append({
                        'keyword': kw, 'trend_code': 2, 'trend_label': '骞崇ǔ',
                        'confidence': 0, 'predicted_hot': 0, 'current_hot': 0, 'change_rate': 0,
                    })
                    continue

                X, current_hot, _ = result
                y_proba = _cls_model.predict_proba(X)[0]
                y_pred = int(np.argmax(y_proba))
                confidence = float(np.max(y_proba))

                predicted_hot = current_hot
                if y_pred == 4:
                    predicted_hot = current_hot * 2.0 if current_hot > 0 else 0.5
                elif y_pred == 3:
                    predicted_hot = current_hot * 1.3
                elif y_pred == 1:
                    predicted_hot = current_hot * 0.5
                elif y_pred == 0:
                    predicted_hot = current_hot * 0.1

                change_rate = (predicted_hot - current_hot) / (current_hot + 1e-6)
                results.append({
                    'keyword': kw,
                    'trend_code': y_pred,
                    'trend_label': _label_map[y_pred],
                    'confidence': round(confidence, 4),
                    'predicted_hot': round(predicted_hot, 4),
                    'current_hot': round(current_hot, 4),
                    'change_rate': round(change_rate, 4),
                })
        finally:
            conn.close()

        return jsonify({'code': 200, 'message': 'success', 'data': {'keywords': results}})
    except Exception as e:
        logger.error(f"鎵归噺棰勬祴鍑洪敊: {e}")
        return jsonify({'code': 500, 'message': str(e), 'data': None}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'predict'})


if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    logger.info(f"鍚姩棰勬祴鏈嶅姟, 绔彛 {port}")
    load_models()
    app.run(host='0.0.0.0', port=port, debug=False)
