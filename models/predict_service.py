#!/usr/bin/env python3
"""
XGBoost 鐑偣棰勬祴 Web 鏈嶅姟 (Flask)
鏀寔 sklearn pickle 鍜?xgb.Booster 涓ょ妯″瀷鏍煎紡
鍩轰簬鏈€杩?1 澶╂暟鎹娴?"""
import os, sys, pickle, json, logging
from datetime import datetime, timedelta
import numpy as np
import xgboost as xgb
import pymysql
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PICKLE_PATH = os.path.join(BASE_DIR, 'hotspot_classifier.pkl')  # 鍏堟鏌?pickle
MODEL_PICKLE_PATH2 = os.path.join(BASE_DIR, 'model.pkl')  # quick_train 杈撳嚭
MODEL_XGB_PATH = os.path.join(BASE_DIR, 'hotspot_classifier.json')   # 鏃ф牸寮?fallback
FEATURE_COLUMNS_PATH = os.path.join(BASE_DIR, 'feature_columns.pkl')
LABEL_ENCODER_PATH = os.path.join(BASE_DIR, 'label_encoder.pkl')
CLASS_MAP_PATH = os.path.join(BASE_DIR, 'class_map.pkl')

DB_CONFIG = {
    'host': '<SERVER_IP>', 'port': 3306,
    'user': 'spark', 'password': '123456',
    'database': 'standardized_data', 'charset': 'utf8mb4',
}

model = None
feature_columns = None
label_encoder = None
class_map = None
model_format = None  # 'pickle' or 'xgb'


def load_model():
    global model, feature_columns, label_encoder, class_map, model_format
    logger.info("Loading model...")

    if os.path.exists(MODEL_PICKLE_PATH):
        with open(MODEL_PICKLE_PATH, 'rb') as f:
            model = pickle.load(f)
        model_format = 'pickle'
        logger.info(f"Loaded from {MODEL_PICKLE_PATH}: {type(model).__name__}")
    elif os.path.exists(MODEL_PICKLE_PATH2):
        with open(MODEL_PICKLE_PATH2, 'rb') as f:
            model = pickle.load(f)
        model_format = 'pickle'
        logger.info(f"Loaded from {MODEL_PICKLE_PATH2}: {type(model).__name__}")
    elif os.path.exists(MODEL_XGB_PATH):
        model = xgb.Booster()
        model.load_model(MODEL_XGB_PATH)
        model_format = 'xgb'
        logger.info(f"Loaded from {MODEL_XGB_PATH}")
    else:
        logger.error("No model file found!")
        return

    if os.path.exists(FEATURE_COLUMNS_PATH):
        with open(FEATURE_COLUMNS_PATH, 'rb') as f:
            feature_columns = pickle.load(f)
    if os.path.exists(LABEL_ENCODER_PATH):
        with open(LABEL_ENCODER_PATH, 'rb') as f:
            label_encoder = pickle.load(f)
    if os.path.exists(CLASS_MAP_PATH):
        with open(CLASS_MAP_PATH, 'rb') as f:
            class_map = pickle.load(f)
    logger.info(f"Ready: {len(feature_columns) if feature_columns else 0} features, format={model_format}")


def query_keyword_data(keyword, days=1):
    end = datetime.now()
    start = end - timedelta(days=days + 1)
    sql = """
        SELECT publish_time, hot_score, hot_raw, like_count, comment_count,
               sentiment_score
        FROM standardized_data
        WHERE keyword = %s AND publish_time >= %s AND publish_time <= %s
        ORDER BY publish_time ASC
    """
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, (keyword, start, end))
            return cur.fetchall()
    finally:
        conn.close()


def compute_features(rows, keyword):
    """Compute all features needed by the model"""
    now = datetime.now()
    # Group into 2h windows
    windows = {}
    for r in rows:
        pt = r['publish_time']
        wh = (pt.hour // 2) * 2
        wstart = pt.replace(hour=wh, minute=0, second=0, microsecond=0)
        windows.setdefault(wstart, []).append(r)

    sorted_wins = sorted(windows.keys())
    if not sorted_wins:
        return None

    target_win = sorted_wins[-1]

    def agg(win_rows):
        n = len(win_rows)
        return {
            'total_hot': sum(r['hot_score'] for r in win_rows),
            'total_hot_raw': sum(r.get('hot_raw', 0) or 0 for r in win_rows),
            'count': n,
            'avg_like': sum(r['like_count'] for r in win_rows) / n,
            'avg_comment': sum(r['comment_count'] for r in win_rows) / n,
            'avg_sentiment': sum(r['sentiment_score'] for r in win_rows) / n,
        }

    win_data = {w: agg(windows[w]) for w in sorted_wins}
    cur = win_data.get(target_win)
    if not cur:
        return None

    win_list = sorted(win_data.keys())
    target_idx = win_list.index(target_win)

    def get_lag(offset, key):
        pos = target_idx - offset
        if 0 <= pos < len(win_list):
            return win_data[win_list[pos]].get(key, 0)
        return 0

    try:
        kw_enc = int(label_encoder.transform([keyword])[0])
    except:
        kw_enc = 0

    feat = {'keyword_enc': kw_enc}
    for k in ['total_hot', 'count', 'avg_like', 'avg_comment', 'avg_sentiment']:
        feat[k] = cur.get(k, 0)

    # Lag 1-3 for all base fields
    for base in ['total_hot', 'avg_sentiment', 'count', 'avg_like', 'avg_comment']:
        for i in range(1, 4):
            feat[f'lag_{i}_{base}'] = get_lag(i, base)

    # Trend features
    lag1 = feat.get('lag_1_total_hot', 0)
    feat['total_hot_change_rate'] = (feat['total_hot'] - lag1) / (lag1 + 1e-6)
    vals = [get_lag(5 - i, 'total_hot') for i in range(6)] + [feat['total_hot']]
    feat['rolling_mean_6_total_hot'] = float(np.mean(vals))
    feat['rolling_std_6_total_hot'] = float(np.std(vals))

    # Time features
    feat['hour'] = target_win.hour
    feat['day_of_week'] = target_win.weekday()
    feat['is_weekend'] = 1 if feat['day_of_week'] >= 5 else 0
    feat['month'] = target_win.month

    return feat, windows, sorted_wins


@app.route('/api/predict/trend', methods=['GET'])
def predict_trend():
    keyword = request.args.get('keyword', '')
    if not keyword:
        return jsonify({'code': 400, 'message': 'keyword is required', 'data': None})

    default_data = {
        'keyword': keyword, 'trend': '骞崇ǔ', 'trend_code': 1, 'probability': 0.5,
        'predicted_change_rate': 0, 'predicted_hot_raw': 0,
        'total_hot': 0, 'total_hot_raw': 0, 'count': 0,
        'message': 'success'
    }

    try:
        rows = query_keyword_data(keyword, days=1)
        if not rows:
            default_data['message'] = '鏃犺冻澶熸暟鎹繘琛岄娴?
            return jsonify({'code': 200, 'message': 'success', 'data': default_data})

        result = compute_features(rows, keyword)
        if result is None or result[0] is None:
            default_data['message'] = '鐗瑰緛璁＄畻澶辫触'
            return jsonify({'code': 200, 'message': 'success', 'data': default_data})

        features, windows, sorted_win_times = result

        # 鏋勫缓鐗瑰緛鍚戦噺骞舵寜妯″瀷瑕佹眰鐨勯『搴忔帓鍒?        feat_values = [features[col] for col in feature_columns]

        if model_format == 'pickle':
            probas = model.predict_proba(np.array([feat_values]))[0]
            probability = float(max(probas))
        else:
            dmatrix = xgb.DMatrix(np.array([feat_values]), feature_names=feature_columns)
            probas = model.predict(dmatrix)
            if len(probas.shape) == 1:
                probability = float(probas[0])
            else:
                probability = float(np.max(probas))

        count = int(features['count'])

        # 瓒嬪娍鏂瑰悜浠庡疄闄呮暟鎹绠楋紙瑙勫垯锛?        recent_windows = sorted_win_times[-2:] if len(sorted_win_times) >= 2 else sorted_win_times[-1:]
        prev_windows = sorted_win_times[-4:-2] if len(sorted_win_times) >= 4 else sorted_win_times[:-1]

        def avg_hot_raw(win_times):
            vals = []
            for wt in win_times:
                for r in windows[wt]:
                    v = r.get('hot_raw', 0) or 0
                    if v > 0:
                        vals.append(v)
            return sum(vals) / len(vals) if vals else 0

        recent_avg = avg_hot_raw(recent_windows)
        prev_avg = avg_hot_raw(prev_windows)

        if prev_avg > 0 and recent_avg > 0:
            change_pct = (recent_avg - prev_avg) / prev_avg
        else:
            change_pct = 0

        if change_pct > 0.05:
            trend, trend_code = '涓婂崌', 2
        elif change_pct < -0.05:
            trend, trend_code = '涓嬮檷', 0
        else:
            trend, trend_code = '骞崇ǔ', 1

        predicted_hot_raw = recent_avg * (1 + change_pct * 0.5) if recent_avg > 0 else 0

        return jsonify({'code': 200, 'message': 'success', 'data': {
            'keyword': keyword, 'window_start': '', 'predict_window_start': '',
            'trend': trend, 'trend_code': trend_code,
            'probability': round(probability, 4),
            'predicted_change_rate': round(change_pct, 4),
            'predicted_hot_raw': round(predicted_hot_raw, 2),
            'total_hot': features['total_hot'],
            'total_hot_raw': features.get('total_hot_raw', features['total_hot']),
            'count': count, 'message': 'success'
        }})

    except Exception as e:
        logger.error(f"Prediction failed: {e}", exc_info=True)
        return jsonify({'code': 500, 'message': f'棰勬祴澶辫触: {str(e)}',
            'data': {**default_data, 'message': f'棰勬祴鏈嶅姟寮傚父: {str(e)}'}})


@app.route('/api/predict/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'model_loaded': model is not None, 'format': model_format})


if __name__ == '__main__':
    load_model()
    app.run(host='0.0.0.0', port=5000, debug=False)
