#!/usr/bin/env python3
"""
XGBoost 鐑偣棰勬祴 Web 鏈嶅姟 (Flask v2)
鏀寔 5-class 瓒嬪娍妯″瀷 (6h绐楀彛) + 鍏煎鍘?2h 鐑偣棰勬祴
"""
import os, pickle, json, logging
from datetime import datetime, timedelta
import numpy as np
import xgboost as xgb
import pymysql
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- 5-class trend model ---
MODEL_5CLASS_PATH = os.path.join(BASE_DIR, 'trend_5class_model.json')
MODEL_META_PATH = os.path.join(BASE_DIR, 'trend_5class_model_meta.json')

# --- Legacy hotspot model ---
MODEL_XGB_PATH = os.path.join(BASE_DIR, 'hotspot_classifier.json')
FEATURE_COLUMNS_PATH = os.path.join(BASE_DIR, 'feature_columns.pkl')
LABEL_ENCODER_PATH = os.path.join(BASE_DIR, 'label_encoder.pkl')

DB_CONFIG = {
    'host': '<SERVER_IP>', 'port': 3306,
    'user': 'spark', 'password': '123456',
    'database': 'standardized_data', 'charset': 'utf8mb4',
}

model_5class = None       # xgb.Booster for 5-class
model_meta = None         # dict with scaler, feature_columns, label_map
model_hotspot = None      # xgb.Booster for hotspot
feature_columns = None    # hotspot feature columns
label_encoder = None      # hotspot label encoder


def load_models():
    global model_5class, model_meta, model_hotspot, feature_columns, label_encoder
    logger.info("Loading models...")

    # 5-class model
    if os.path.exists(MODEL_5CLASS_PATH):
        model_5class = xgb.Booster()
        model_5class.load_model(MODEL_5CLASS_PATH)
        logger.info(f"5-class model loaded from {MODEL_5CLASS_PATH}")
    else:
        logger.warning("5-class model not found")

    if os.path.exists(MODEL_META_PATH):
        with open(MODEL_META_PATH) as f:
            model_meta = json.load(f)
        logger.info(f"5-class meta loaded, {len(model_meta.get('feature_columns', []))} features")

    # Hotspot model (legacy)
    if os.path.exists(MODEL_XGB_PATH):
        model_hotspot = xgb.Booster()
        model_hotspot.load_model(MODEL_XGB_PATH)
        logger.info("Hotspot model loaded")
    if os.path.exists(FEATURE_COLUMNS_PATH):
        with open(FEATURE_COLUMNS_PATH, 'rb') as f:
            feature_columns = pickle.load(f)
    if os.path.exists(LABEL_ENCODER_PATH):
        with open(LABEL_ENCODER_PATH, 'rb') as f:
            label_encoder = pickle.load(f)


def get_conn():
    return pymysql.connect(**DB_CONFIG)


# ========== 5-class trend feature engineering (6h windows) ==========

def query_6h_data(keyword):
    """Query last 7 days of data for 6h-window feature computation"""
    end = datetime.now()
    start = end - timedelta(days=7)
    sql = """
        SELECT publish_time, hot_score, hot_raw, like_count, comment_count,
               view_count, coin_count, favorite_count, share_count,
               sentiment_score
        FROM standardized_data
        WHERE keyword = %s AND publish_time >= %s AND publish_time <= %s
        ORDER BY publish_time ASC
    """
    conn = get_conn()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, (keyword, start, end))
            return cur.fetchall()
    finally:
        conn.close()


def compute_features_6h(rows, keyword):
    """Compute 5-class model features using 6h windows (matches train_xgboost_5class.py)"""
    if not rows:
        return None

    # Aggregate into 6h windows
    windows = {}
    for r in rows:
        pt = r['publish_time']
        wh = (pt.hour // 6) * 6
        wstart = pt.replace(hour=wh, minute=0, second=0, microsecond=0)
        windows.setdefault(wstart, []).append(r)

    sorted_wins = sorted(windows.keys())
    if len(sorted_wins) < 2:
        return None

    target_win = sorted_wins[-1]

    def agg(win_rows):
        n = len(win_rows)
        return {
            'total_hot': sum(r['hot_score'] for r in win_rows),
            'mean_hot': np.mean([r['hot_score'] for r in win_rows]) if n else 0,
            'max_hot': max(r['hot_score'] for r in win_rows) if n else 0,
            'log_total_hot': np.log1p(sum(r['hot_score'] for r in win_rows)),
            'total_like': sum(r['like_count'] for r in win_rows),
            'total_comment': sum(r['comment_count'] for r in win_rows),
            'total_view': sum(r.get('view_count', 0) or 0 for r in win_rows),
            'total_coin': sum(r.get('coin_count', 0) or 0 for r in win_rows),
            'total_favorite': sum(r.get('favorite_count', 0) or 0 for r in win_rows),
            'total_share': sum(r.get('share_count', 0) or 0 for r in win_rows),
            'avg_sentiment': np.mean([r['sentiment_score'] for r in win_rows]) if n else 0,
            'count': n,
        }

    win_data = {}
    for w in sorted_wins:
        win_data[w] = agg(windows[w])

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

    # keyword encoding
    try:
        kw_enc = int(label_encoder.transform([keyword])[0])
    except:
        kw_enc = 0

    # Build feature dict matching the 5-class model's feature_columns
    feat = {'keyword_enc': kw_enc}
    for k in ['total_hot', 'mean_hot', 'max_hot', 'log_total_hot',
              'total_like', 'total_comment', 'total_view', 'total_coin',
              'total_favorite', 'total_share', 'avg_sentiment', 'count']:
        feat[k] = cur.get(k, 0)

    # Lag features: lag_{1,2,3,6}_{total_hot, count, total_comment}
    for lag in [1, 2, 3, 6]:
        feat[f'lag_{lag}_total_hot'] = get_lag(lag, 'total_hot')
        feat[f'lag_{lag}_count'] = get_lag(lag, 'count')
        feat[f'lag_{lag}_total_comment'] = get_lag(lag, 'total_comment')

    # Change rates
    lag1_hot = feat.get('lag_1_total_hot', 0)
    lag1_count = feat.get('lag_1_count', 0)
    feat['hot_change_rate'] = (feat['total_hot'] - lag1_hot) / (lag1_hot + 1e-6)
    feat['count_change_rate'] = (feat['count'] - lag1_count) / (lag1_count + 1e-6)

    # Trend up count: how many of last 3 windows had positive hot_change_rate
    up_count = 0
    for i in range(1, 4):
        prev_hot = get_lag(i, 'total_hot')
        prev_prev = get_lag(i + 1, 'total_hot')
        if (prev_hot - prev_prev) > 0:
            up_count += 1
    feat['trend_up_count'] = up_count

    # Rolling stats over last 3 and 6 windows
    for w in [3, 6]:
        vals = [get_lag(w - 1 - i, 'total_hot') for i in range(w - 1)]
        vals.append(feat['total_hot'])
        feat[f'rolling_mean_{w}_total_hot'] = float(np.mean(vals))
        if len(vals) > 1:
            feat[f'rolling_max_{w}_total_hot'] = float(max(vals))
        else:
            feat[f'rolling_max_{w}_total_hot'] = float(vals[0]) if vals else 0

    # Time features
    feat['hour'] = target_win.hour
    feat['day_of_week'] = target_win.weekday()
    feat['is_weekend'] = 1 if feat['day_of_week'] >= 5 else 0
    feat['month'] = target_win.month

    return feat


# ========== 5-class prediction ==========

PREDEFINED_CHANGE_RATES = {
    0: -0.60,  # 鏆磋穼
    1: -0.25,  # 涓嬮檷
    2: 0.0,    # 骞崇ǔ
    3: 0.35,   # 涓婂崌
    4: 1.50,   # 鏆存定
}

LABEL_MAP = {
    0: '鏆磋穼', 1: '涓嬮檷', 2: '骞崇ǔ', 3: '涓婂崌', 4: '鏆存定'
}
TREND_CODE_MAP = {
    0: 0, 1: 0, 2: 1, 3: 2, 4: 2
}


def predict_trend_5class(keyword):
    """Predict 6h trend using 5-class model"""
    if model_5class is None:
        return None

    rows = query_6h_data(keyword)
    if not rows:
        return None

    features = compute_features_6h(rows, keyword)
    if features is None:
        return None

    # Get feature columns from meta
    fc = model_meta.get('feature_columns', [])
    # Build feature vector, fill missing with 0
    feat_values = []
    for col in fc:
        feat_values.append(features.get(col, 0))

    # Apply RobustScaler
    center = np.array(model_meta.get('scaler_center', []))
    scale = np.array(model_meta.get('scaler_scale', []))
    if len(center) == len(feat_values) and len(scale) == len(feat_values):
        feat_values = (np.array(feat_values) - center) / (scale + 1e-10)

    dmatrix = xgb.DMatrix(np.array([feat_values]), feature_names=fc)
    probas = model_5class.predict(dmatrix)[0]
    pred_class = int(np.argmax(probas))
    probability = float(probas[pred_class])

    # Map to response
    trend = LABEL_MAP.get(pred_class, '骞崇ǔ')
    trend_code = TREND_CODE_MAP.get(pred_class, 1)
    change_rate = PREDEFINED_CHANGE_RATES.get(pred_class, 0)

    predicted_hot_raw = features['total_hot'] * (1 + change_rate)
    total_hot_raw = features['total_hot']

    return {
        'keyword': keyword,
        'trend': trend,
        'trend_code': trend_code,
        'probability': round(probability, 4),
        'predicted_change_rate': round(change_rate, 4),
        'predicted_hot_raw': round(predicted_hot_raw, 2),
        'total_hot': total_hot_raw,
        'total_hot_raw': total_hot_raw,
        'count': features.get('count', 0),
        'model': '5class',
    }


# ========== Legacy 2h trend prediction (from original predict_service.py) ==========

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
    conn = get_conn()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, (keyword, start, end))
            return cur.fetchall()
    finally:
        conn.close()


def compute_features_2h(rows, keyword):
    now = datetime.now()
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

    for base in ['total_hot', 'avg_sentiment', 'count', 'avg_like', 'avg_comment']:
        for i in range(1, 4):
            feat[f'lag_{i}_{base}'] = get_lag(i, base)

    lag1 = feat.get('lag_1_total_hot', 0)
    feat['total_hot_change_rate'] = (feat['total_hot'] - lag1) / (lag1 + 1e-6)
    vals = [get_lag(5 - i, 'total_hot') for i in range(6)] + [feat['total_hot']]
    feat['rolling_mean_6_total_hot'] = float(np.mean(vals))
    feat['rolling_std_6_total_hot'] = float(np.std(vals))

    feat['hour'] = target_win.hour
    feat['day_of_week'] = target_win.weekday()
    feat['is_weekend'] = 1 if feat['day_of_week'] >= 5 else 0
    feat['month'] = target_win.month

    return feat, windows, sorted_wins


# ========== API endpoints ==========

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
        # Try 5-class model first
        result_5class = predict_trend_5class(keyword)
        if result_5class:
            return jsonify({'code': 200, 'message': 'success', 'data': result_5class})

        # Fallback to legacy 2h hotspot
        rows = query_keyword_data(keyword, days=1)
        if not rows:
            default_data['message'] = '鏃犺冻澶熸暟鎹繘琛岄娴?
            return jsonify({'code': 200, 'message': 'success', 'data': default_data})

        result = compute_features_2h(rows, keyword)
        if result is None or result[0] is None:
            default_data['message'] = '鐗瑰緛璁＄畻澶辫触'
            return jsonify({'code': 200, 'message': 'success', 'data': default_data})

        features, windows, sorted_win_times = result

        # Build feature vector
        feat_values = [features[col] for col in feature_columns]
        dmatrix = xgb.DMatrix(np.array([feat_values]), feature_names=feature_columns)
        probas = model_hotspot.predict(dmatrix)
        if len(probas.shape) == 1:
            probability = float(probas[0])
        else:
            probability = float(np.max(probas))

        count = int(features['count'])

        # Trend direction from data
        recent_windows = sorted_win_times[-2:] if len(sorted_win_times) >= 2 else sorted_win_times[-1:]
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
            'count': count, 'message': 'success', 'model': 'legacy_2h'
        }})

    except Exception as e:
        logger.error(f"Prediction failed: {e}", exc_info=True)
        return jsonify({'code': 500, 'message': f'棰勬祴澶辫触: {str(e)}',
            'data': {**default_data, 'message': f'棰勬祴鏈嶅姟寮傚父: {str(e)}'}})


@app.route('/api/predict/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'model_5class': model_5class is not None,
        'model_hotspot': model_hotspot is not None,
    })


if __name__ == '__main__':
    load_models()
    app.run(host='0.0.0.0', port=5000, debug=False)
