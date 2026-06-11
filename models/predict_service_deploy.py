#!/usr/bin/env python3
"""
瀹炴椂瓒嬪娍棰勬祴鏈嶅姟 - XGBoost 2h绐楀彛涓夊垎绫绘ā鍨?鍔犺浇鏈€浣虫ā鍨嬶紙trend_classifier_best锛夛紝鎻愪緵HTTP API渚汮ava鍚庣璋冪敤
"""
import os, pickle, json, logging
from datetime import datetime, timedelta
import numpy as np
import pymysql
from xgboost import XGBClassifier
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')
MODEL_PATH = os.path.join(MODEL_DIR, 'trend_classifier_best.json')
FEATURE_PATH = os.path.join(MODEL_DIR, 'trend_feature_columns_best.pkl')
ENCODER_PATH = os.path.join(MODEL_DIR, 'trend_label_encoder_best.pkl')
CLASS_MAP_PATH = os.path.join(MODEL_DIR, 'trend_class_map_best.pkl')

DB_CONFIG = {
    'host': '<SERVER_IP>', 'port': 3306,
    'user': 'spark', 'password': '123456',
    'database': 'standardized_data', 'charset': 'utf8mb4',
}

model = None
feature_columns = None
label_encoder = None
class_map = None

TREND_LABEL_MAP = {'涓嬮檷': '涓嬮檷', '骞崇ǔ': '骞崇ǔ', '涓婂崌': '澧為暱'}
TREND_CODE_MAP = {'涓嬮檷': 0, '骞崇ǔ': 2, '涓婂崌': 3}


def load_models():
    global model, feature_columns, label_encoder, class_map
    logger.info("Loading model files from %s", MODEL_DIR)

    model = XGBClassifier()
    model.load_model(MODEL_PATH)
    logger.info("Model loaded: %s", MODEL_PATH)

    with open(FEATURE_PATH, 'rb') as f:
        feature_columns = pickle.load(f)
    logger.info("Features loaded: %d columns", len(feature_columns))

    with open(ENCODER_PATH, 'rb') as f:
        label_encoder = pickle.load(f)
    logger.info("LabelEncoder loaded")

    with open(CLASS_MAP_PATH, 'rb') as f:
        class_map = pickle.load(f)
    logger.info("Class map loaded: %s", class_map)


def get_db():
    return pymysql.connect(cursorclass=pymysql.cursors.DictCursor, **DB_CONFIG)


def get_latest_window(keyword):
    """鑾峰彇鎸囧畾鍏抽敭璇嶆渶鏂扮殑2h绐楀彛鏃堕棿"""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT MAX(publish_time) as t
                FROM standardized_data
                WHERE keyword = %s
            """, (keyword,))
            row = cur.fetchone()
        if row and row['t']:
            t = row['t']
            if isinstance(t, datetime):
                return t
        return None
    except Exception as e:
        logger.error("DB error: %s", e)
        return None
    finally:
        conn.close()


def load_window_data(keyword, window_start):
    """鍔犺浇鏈€杩?澶╂暟鎹敤浜庣壒寰佸伐绋?""
    start = window_start - timedelta(days=3)
    end = window_start + timedelta(hours=2)
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT publish_time, hot_score, hot_raw, like_count, comment_count,
                       sentiment_score
                FROM standardized_data
                WHERE keyword = %s AND publish_time >= %s AND publish_time < %s
                ORDER BY publish_time
            """, (keyword, start, end))
            rows = cur.fetchall()
        return rows
    except Exception as e:
        logger.error("DB error: %s", e)
        return []
    finally:
        conn.close()


def build_feature(keyword, rows, window_start):
    """鐗瑰緛宸ョ▼锛屼笌璁粌鑴氭湰淇濇寔涓€鑷?""
    if not rows:
        return None

    # 鎸?h绐楀彛鍒嗙粍
    windows = {}
    for r in rows:
        t = r['publish_time']
        if isinstance(t, datetime):
            wh = t.hour - (t.hour % 2)
            wt = t.replace(hour=wh, minute=0, second=0, microsecond=0)
        else:
            continue
        windows.setdefault(wt, []).append(r)

    sorted_ws = sorted(windows.keys())
    if not sorted_ws:
        return None

    # 鎵惧埌褰撳墠绐楀彛
    cur_idx = -1
    for i, w in enumerate(sorted_ws):
        if w <= window_start:
            cur_idx = i
    if cur_idx < 0:
        return None

    cur_w = sorted_ws[cur_idx]
    cur_data = windows[cur_w]
    count = len(cur_data)
    total_hot = sum(r['hot_score'] or 0 for r in cur_data)
    total_hot_raw = sum(r['hot_raw'] or 0 for r in cur_data)
    avg_like = sum(r['like_count'] or 0 for r in cur_data) / count
    avg_comment = sum(r['comment_count'] or 0 for r in cur_data) / count
    avg_sentiment = sum(r['sentiment_score'] or 0 for r in cur_data) / count

    hour = cur_w.hour
    day_of_week = cur_w.weekday()
    is_weekend = 1 if day_of_week >= 5 else 0
    month = cur_w.month

    try:
        keyword_enc = int(label_encoder.transform([keyword])[0])
    except Exception:
        keyword_enc = 0

    # lag鐗瑰緛
    lag_features = {}
    for lag in [1, 2, 3]:
        idx = cur_idx - lag
        if idx >= 0 and idx < len(sorted_ws):
            wd = windows.get(sorted_ws[idx], [])
            if wd:
                lag_features[f'lag_{lag}_total_hot'] = sum(r['hot_score'] or 0 for r in wd)
                lag_features[f'lag_{lag}_avg_like'] = sum(r['like_count'] or 0 for r in wd) / len(wd)
                lag_features[f'lag_{lag}_avg_comment'] = sum(r['comment_count'] or 0 for r in wd) / len(wd)
                lag_features[f'lag_{lag}_avg_sentiment'] = sum(r['sentiment_score'] or 0 for r in wd) / len(wd)
            else:
                lag_features[f'lag_{lag}_total_hot'] = 0
                lag_features[f'lag_{lag}_avg_like'] = 0
                lag_features[f'lag_{lag}_avg_comment'] = 0
                lag_features[f'lag_{lag}_avg_sentiment'] = 0
        else:
            lag_features[f'lag_{lag}_total_hot'] = 0
            lag_features[f'lag_{lag}_avg_like'] = 0
            lag_features[f'lag_{lag}_avg_comment'] = 0
            lag_features[f'lag_{lag}_avg_sentiment'] = 0

    lag_1 = lag_features.get('lag_1_total_hot', 0)
    change_rate = (total_hot - lag_1) / (lag_1 + 1e-6)

    # 婊氬姩缁熻锛堟渶杩?涓獥鍙ｏ級
    roll_wins = sorted_ws[max(0, cur_idx - 5):cur_idx]
    if roll_wins:
        roll_hots = [sum(windows[sw][r]['hot_score'] or 0 for r in range(len(windows[sw]))) for sw in roll_wins]
        rolling_mean = float(np.mean(roll_hots)) if roll_hots else 0
        rolling_std = float(np.std(roll_hots)) if roll_hots else 0
    else:
        rolling_mean = 0
        rolling_std = 0

    feat = {
        'keyword_enc': keyword_enc,
        'total_hot': total_hot,
        'total_hot_raw': total_hot_raw,
        'count': count,
        'avg_like': avg_like,
        'avg_comment': avg_comment,
        'avg_sentiment': avg_sentiment,
        'lag_1_total_hot': lag_features.get('lag_1_total_hot', 0),
        'lag_2_total_hot': lag_features.get('lag_2_total_hot', 0),
        'lag_3_total_hot': lag_features.get('lag_3_total_hot', 0),
        'lag_1_avg_like': lag_features.get('lag_1_avg_like', 0),
        'lag_2_avg_like': lag_features.get('lag_2_avg_like', 0),
        'lag_3_avg_like': lag_features.get('lag_3_avg_like', 0),
        'lag_1_avg_comment': lag_features.get('lag_1_avg_comment', 0),
        'lag_2_avg_comment': lag_features.get('lag_2_avg_comment', 0),
        'lag_3_avg_comment': lag_features.get('lag_3_avg_comment', 0),
        'lag_1_avg_sentiment': lag_features.get('lag_1_avg_sentiment', 0),
        'lag_2_avg_sentiment': lag_features.get('lag_2_avg_sentiment', 0),
        'lag_3_avg_sentiment': lag_features.get('lag_3_avg_sentiment', 0),
        'total_hot_change_rate': change_rate,
        'rolling_mean_6_total_hot': rolling_mean,
        'rolling_std_6_total_hot': rolling_std,
        'hour': hour,
        'day_of_week': day_of_week,
        'is_weekend': is_weekend,
        'month': month,
    }
    return feat


def predict_trend(keyword):
    logger.info("Predict: keyword=%s", keyword)

    latest = get_latest_window(keyword)
    if latest is None:
        logger.warning("No data for keyword: %s", keyword)
        return None

    # 瀵归綈鍒?h绐楀彛
    wh = latest.hour - (latest.hour % 2)
    window_start = latest.replace(hour=wh, minute=0, second=0, microsecond=0)

    rows = load_window_data(keyword, window_start)
    feat = build_feature(keyword, rows, window_start)
    if feat is None:
        logger.warning("Feature engineering failed for: %s", keyword)
        return None

    # 棰勬祴
    vals = np.array([[feat[c] for c in feature_columns]])
    pred = int(model.predict(vals)[0])
    proba = model.predict_proba(vals)[0]
    prob = float(max(proba))

    # 鏄犲皠缁撴灉
    raw_label = class_map.get(pred, '骞崇ǔ')
    trend_label = TREND_LABEL_MAP.get(raw_label, '骞崇ǔ')
    trend_code = TREND_CODE_MAP.get(raw_label, 2)

    # 鏄剧ず鐑害鍊肩敤 hot_raw锛堟ā鍨嬬壒寰佷粛鐢?hot_score锛?    current_hot = float(feat['total_hot_raw'])

    result = {
        'keyword': keyword,
        'trend_code': trend_code,
        'trend_label': trend_label,
        'predicted_hot': current_hot,
        'current_hot': current_hot,
        'change_rate': float(feat['total_hot_change_rate']),
        'strategy': 'XGBoost 2h绐楀彛涓夊垎绫?,
    }
    logger.info("Result: %s", result)
    return result


@app.route('/api/predict/trend', methods=['GET'])
def predict_api():
    keyword = request.args.get('keyword', '')
    if not keyword:
        return jsonify({'code': 400, 'message': 'keyword required', 'data': None}), 400
    try:
        result = predict_trend(keyword)
        if result is None:
            return jsonify({'code': 404, 'message': 'no data', 'data': None})
        return jsonify({'code': 200, 'message': 'success', 'data': result})
    except Exception as e:
        logger.error("Prediction error: %s", e)
        return jsonify({'code': 500, 'message': str(e), 'data': None}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'model': 'trend_classifier_best'})


if __name__ == '__main__':
    load_models()
    app.run(host='0.0.0.0', port=5000, debug=False)
