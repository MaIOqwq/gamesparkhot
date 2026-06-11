#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
瀹炴椂瓒嬪娍棰勬祴鏈嶅姟 - 浣跨敤XGBoost妯″瀷棰勬祴2灏忔椂鐑害瓒嬪娍
鏀寔鏁版嵁搴撲腑娌℃湁褰撳墠鏃堕棿鏁版嵁鐨勬儏鍐碉紝浣跨敤鏁版嵁搴撲腑鏈€鏂扮殑鏁版嵁鏃堕棿浣滀负鍙傝€?"""

import os
import pickle
import json
import logging
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import numpy as np
import pymysql
from xgboost import XGBClassifier

# 閰嶇疆鏃ュ織
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 妯″瀷鐩稿叧鍏ㄥ眬鍙橀噺
model = None
feature_columns = None
label_encoder = None
class_map = None

def load_models(model_dir: str):
    """鍔犺浇鎵€鏈夋ā鍨嬫枃浠?""
    global model, feature_columns, label_encoder, class_map

    logger.info("寮€濮嬪姞杞芥ā鍨嬫枃浠?..")

    # 鍔犺浇XGBoost妯″瀷
    model_path = os.path.join(model_dir, 'trend_classifier_2h.json')
    model = XGBClassifier()
    model.load_model(model_path)
    logger.info(f"妯″瀷鍔犺浇鎴愬姛: {model_path}")

    # 鍔犺浇鐗瑰緛鍒楀悕
    feature_path = os.path.join(model_dir, 'trend_feature_columns_2h.pkl')
    with open(feature_path, 'rb') as f:
        feature_columns = pickle.load(f)
    logger.info(f"鐗瑰緛鍒楀姞杞芥垚鍔? {feature_path}, 鍏?{len(feature_columns)} 涓壒寰?)

    # 鍔犺浇LabelEncoder
    encoder_path = os.path.join(model_dir, 'trend_label_encoder_2h.pkl')
    with open(encoder_path, 'rb') as f:
        label_encoder = pickle.load(f)
    logger.info(f"LabelEncoder鍔犺浇鎴愬姛: {encoder_path}")

    # 鍔犺浇绫诲埆鏄犲皠
    class_map_path = os.path.join(model_dir, 'trend_class_map_2h.pkl')
    with open(class_map_path, 'rb') as f:
        class_map = pickle.load(f)
    logger.info(f"绫诲埆鏄犲皠鍔犺浇鎴愬姛: {class_map_path}, 鏄犲皠: {class_map}")

def get_db_connection():
    """鑾峰彇鏁版嵁搴撹繛鎺?""
    return pymysql.connect(
        host='<SERVER_IP>',
        port=3306,
        user='spark',
        password = <DB_PASSWORD>,
        database='standardized_data',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def get_latest_data_time(keyword: str):
    """鑾峰彇鏁版嵁搴撲腑鎸囧畾鍏抽敭璇嶇殑鏈€鏂版暟鎹椂闂?""
    try:
        conn = get_db_connection()
        query = f"""
            SELECT MAX(publish_time) as latest_time
            FROM standardized_data
            WHERE keyword = '{keyword}'
        """
        with conn.cursor() as cursor:
            cursor.execute(query)
            result = cursor.fetchone()
        conn.close()

        if result and result['latest_time']:
            return result['latest_time']
        return None
    except Exception as e:
        logger.error(f"鑾峰彇鏈€鏂版暟鎹椂闂村け璐? {e}")
        return None

def load_data_from_db(keyword: str, window_start: datetime):
    """浠庢暟鎹簱鍔犺浇鎸囧畾鍏抽敭璇嶅拰绐楀彛鐨勬暟鎹?
    Args:
        keyword: 鍏抽敭璇?        window_start: 褰撳墠棰勬祴绐楀彛寮€濮嬫椂闂?
    Returns:
        list: 鏁版嵁琛屽垪琛?    """
    logger.info(f"浠庢暟鎹簱鍔犺浇鏁版嵁: 鍏抽敭璇?{keyword}, 绐楀彛={window_start}")

    # 璁＄畻鏃堕棿鑼冨洿锛氬綋鍓嶇獥鍙ｅ墠3澶╁埌褰撳墠绐楀彛鍚?灏忔椂
    start_time = window_start - timedelta(days=3)
    end_time = window_start + timedelta(hours=2)

    try:
        conn = get_db_connection()
        query = f"""
            SELECT
                keyword, publish_time, hot_score, hot_raw, like_count, comment_count,
                view_count, coin_count, favorite_count, share_count, danmaku_count,
                sentiment_score, author_fans, author_level, author_post_count,
                has_image, has_video
            FROM standardized_data
            WHERE keyword = '{keyword}'
            AND publish_time >= '{start_time}'
            AND publish_time < '{end_time}'
            ORDER BY publish_time
        """

        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        conn.close()
        logger.info(f"鏁版嵁鍔犺浇瀹屾垚: 鍏?{len(rows)} 鏉¤褰?)
        return rows

    except Exception as e:
        logger.error(f"鏁版嵁鍔犺浇澶辫触: {e}")
        import traceback
        traceback.print_exc()
        return []

def feature_engineering(rows, window_start, keyword):
    """鐗瑰緛宸ョ▼ - 涓哄綋鍓嶇獥鍙ｇ敓鎴愮壒寰佸悜閲?
    Args:
        rows: 鏁版嵁搴撲腑鐨勫師濮嬫暟鎹
        window_start: 褰撳墠棰勬祴绐楀彛寮€濮嬫椂闂?        keyword: 鍏抽敭璇?
    Returns:
        dict: 鐗瑰緛鍚戦噺瀛楀吀
    """
    logger.info("寮€濮嬬壒寰佸伐绋?..")

    if not rows:
        logger.warning("娌℃湁鏁版嵁鍙敤浜庣壒寰佸伐绋?)
        return None

    # 鎸夌獥鍙ｅ垎缁勮仛鍚?    window_data = {}
    for row in rows:
        pub_time = row['publish_time']
        # 璁＄畻2灏忔椂绐楀彛
        window_hour = pub_time.hour - (pub_time.hour % 2)
        window_time = pub_time.replace(hour=window_hour, minute=0, second=0, microsecond=0)

        if window_time not in window_data:
            window_data[window_time] = []
        window_data[window_time].append(row)

    # 鑾峰彇鎵€鏈夌獥鍙ｇ殑鎺掑簭鍒楄〃
    sorted_windows = sorted(window_data.keys())

    if not sorted_windows:
        logger.warning("娌℃湁绐楀彛鏁版嵁")
        return None

    # 鎵惧埌鏈€鎺ヨ繎褰撳墠绐楀彛鐨勫巻鍙茬獥鍙?    current_window_data = None
    current_idx = -1

    for i, w in enumerate(sorted_windows):
        if w <= window_start:
            current_window_data = window_data[w]
            current_idx = i
        else:
            break

    if current_window_data is None or current_idx < 0:
        logger.warning(f"娌℃湁鎵惧埌鏃╀簬 {window_start} 鐨勭獥鍙ｆ暟鎹?)
        return None

    # 浣跨敤瀹為檯鎵惧埌鐨勭獥鍙ｆ椂闂?    actual_window_start = sorted_windows[current_idx]
    logger.info(f"瀹為檯浣跨敤鐨勭獥鍙ｆ椂闂? {actual_window_start}")

    # 璁＄畻鑱氬悎鐗瑰緛
    total_hot = sum(row['hot_score'] for row in current_window_data)
    total_hot_raw = sum(row.get('hot_raw', 0) or 0 for row in current_window_data)
    count = len(current_window_data)
    avg_like = sum(row['like_count'] for row in current_window_data) / count
    avg_comment = sum(row['comment_count'] for row in current_window_data) / count
    avg_sentiment = sum(row['sentiment_score'] for row in current_window_data) / count

    # 鏃堕棿鐗瑰緛
    hour = actual_window_start.hour
    day_of_week = actual_window_start.weekday()  # 0-6
    is_weekend = 1 if day_of_week >= 5 else 0
    month = actual_window_start.month

    # 鍏抽敭璇嶇紪鐮?    try:
        keyword_enc = label_encoder.transform([keyword])[0]
    except:
        logger.warning(f"鍏抽敭璇?'{keyword}' 涓嶅湪璁粌闆嗕腑锛屼娇鐢?")
        keyword_enc = 0

    # 璁＄畻鍘嗗彶婊戝姩绐楀彛鐗瑰緛锛坙ag_1, lag_2, lag_3锛?    lag_features = {}
    for lag in [1, 2, 3]:
        lag_idx = current_idx - lag
        if lag_idx >= 0:
            lag_window = sorted_windows[lag_idx]
            lag_data = window_data.get(lag_window, [])
            if lag_data:
                lag_features[f'lag_{lag}_total_hot'] = sum(row['hot_score'] for row in lag_data)
                lag_features[f'lag_{lag}_avg_like'] = sum(row['like_count'] for row in lag_data) / len(lag_data)
                lag_features[f'lag_{lag}_avg_comment'] = sum(row['comment_count'] for row in lag_data) / len(lag_data)
                lag_features[f'lag_{lag}_avg_sentiment'] = sum(row['sentiment_score'] for row in lag_data) / len(lag_data)
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

    # 璁＄畻鐑害鍙樺寲鐜?    lag_1_total_hot = lag_features.get('lag_1_total_hot', 0)
    total_hot_change_rate = (total_hot - lag_1_total_hot) / (lag_1_total_hot + 1e-6)

    # 璁＄畻婊氬姩鍧囧€煎拰鏍囧噯宸紙鏈€杩?涓獥鍙ｏ級
    rolling_windows = sorted_windows[max(0, current_idx - 5):current_idx]
    if rolling_windows:
        rolling_total_hots = [sum(row['hot_score'] for row in window_data[sw]) for sw in rolling_windows]
        rolling_mean_6_total_hot = np.mean(rolling_total_hots) if rolling_total_hots else 0
        rolling_std_6_total_hot = np.std(rolling_total_hots) if rolling_total_hots else 0
    else:
        rolling_mean_6_total_hot = 0
        rolling_std_6_total_hot = 0

    # 鏋勯€犵壒寰佸悜閲忥紙鎸夌収璁粌鏃剁殑鐗瑰緛椤哄簭锛?    feature = {
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
        'total_hot_change_rate': total_hot_change_rate,
        'rolling_mean_6_total_hot': rolling_mean_6_total_hot,
        'rolling_std_6_total_hot': rolling_std_6_total_hot,
        'hour': hour,
        'day_of_week': day_of_week,
        'is_weekend': is_weekend,
        'month': month
    }

    logger.info(f"鐗瑰緛宸ョ▼瀹屾垚: 褰撳墠绐楀彛={actual_window_start}, 鎬荤儹搴?{total_hot}, 鏁版嵁鏉℃暟={count}")
    return feature

def predict_trend(keyword: str):
    """棰勬祴鎸囧畾鍏抽敭璇嶇殑2灏忔椂鍚庣儹搴﹁秼鍔?
    Args:
        keyword: 鍏抽敭璇?
    Returns:
        dict: 棰勬祴缁撴灉锛屽寘鍚秼鍔跨被鍒拰姒傜巼
    """
    global model, feature_columns, label_encoder, class_map

    logger.info(f"寮€濮嬮娴嬭秼鍔? 鍏抽敭璇?{keyword}")

    # 棣栧厛鑾峰彇鏁版嵁搴撲腑鏈€鏂扮殑鏁版嵁鏃堕棿
    latest_time = get_latest_data_time(keyword)

    if latest_time is None:
        logger.warning(f"娌℃湁鎵惧埌鍏抽敭璇?'{keyword}' 鐨勪换浣曟暟鎹?)
        return {
            'keyword': keyword,
            'window_start': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'trend': '鏈煡',
            'trend_code': -1,
            'probability': 0.0,
            'message': '娌℃湁瓒冲鐨勬暟鎹繘琛岄娴?
        }

    logger.info(f"鏁版嵁搴撲腑鏈€鏂扮殑鏁版嵁鏃堕棿: {latest_time}")

    # 浣跨敤鏈€鏂版暟鎹椂闂翠綔涓哄弬鑰冪偣锛屾壘鍒版渶杩戠殑2灏忔椂绐楀彛
    latest_datetime = latest_time if isinstance(latest_time, datetime) else latest_time.to_pydatetime()
    hours = latest_datetime.hour - (latest_datetime.hour % 2)
    window_start = latest_datetime.replace(hour=hours, minute=0, second=0, microsecond=0)

    # 璁＄畻涓嬩竴涓?灏忔椂绐楀彛锛堥娴嬬洰鏍囷級
    predict_window_start = window_start + timedelta(hours=2)

    logger.info(f"褰撳墠绐楀彛: {window_start}, 棰勬祴绐楀彛: {predict_window_start}")

    # 浠庢暟鎹簱鍔犺浇鏁版嵁
    rows = load_data_from_db(keyword, window_start)

    if not rows:
        logger.warning(f"娌℃湁鎵惧埌鍏抽敭璇?'{keyword}' 鍦?{window_start} 闄勮繎鐨勬暟鎹?)
        return {
            'keyword': keyword,
            'window_start': window_start.strftime('%Y-%m-%d %H:%M:%S'),
            'trend': '鏈煡',
            'trend_code': -1,
            'probability': 0.0,
            'message': '娌℃湁瓒冲鐨勬暟鎹繘琛岄娴?
        }

    # 鐗瑰緛宸ョ▼
    feature = feature_engineering(rows, window_start, keyword)

    if feature is None:
        return {
            'keyword': keyword,
            'window_start': window_start.strftime('%Y-%m-%d %H:%M:%S'),
            'trend': '鏈煡',
            'trend_code': -1,
            'probability': 0.0,
            'message': '鐗瑰緛宸ョ▼澶辫触'
        }

    # 鍑嗗鐗瑰緛鐭╅樀
    feature_values = [feature[col] for col in feature_columns]
    feature_matrix = np.array([feature_values])

    # 棰勬祴
    prediction = model.predict(feature_matrix)[0]
    probability = model.predict_proba(feature_matrix)[0]

    # 鑾峰彇棰勬祴缁撴灉
    trend = class_map.get(int(prediction), '鏈煡')
    prob = float(probability[int(prediction)])

    # 鏍规嵁妯″瀷棰勬祴缁撴灉浼扮畻鍙樺寲鐜?    # 璁粌鏃跺垎绫婚槇鍊硷細涓婂崌 > +10%锛屼笅闄?< -10%
    # 鍙栧悇绫诲埆鐨勪唬琛ㄦ€у彉鍖栫巼杩涜姒傜巼鍔犳潈
    change_rate_map = {0: -0.15, 1: 0.0, 2: 0.15}
    sorted_classes = sorted(class_map.keys())
    weighted_change_rate = sum(
        change_rate_map.get(c, 0.0) * float(probability[i])
        for i, c in enumerate(sorted_classes)
    )
    # 楂樼疆淇″害鏃剁洿鎺ヤ娇鐢ㄨ绫诲埆鐨勫彉鍖栫巼锛岄伩鍏嶈浣庢鐜囩被鍒媺浣?    pred_class = int(prediction)
    if prob > 0.8:
        weighted_change_rate = change_rate_map.get(pred_class, 0.0)

    logger.info(f"棰勬祴缁撴灉: 瓒嬪娍={trend}, 姒傜巼={prob:.4f}, 鍙樺寲鐜?{weighted_change_rate:.4f}")

    # 璁＄畻棰勬祴鍚庣殑鐑害鍊硷紙hot_raw 鍘熷鐑害锛屼笌鍥捐〃鍚屽昂搴︼級
    total_hot_raw = feature.get('total_hot_raw', 0) or 0
    predicted_hot_raw = int(total_hot_raw * (1 + weighted_change_rate))

    return {
        'keyword': keyword,
        'window_start': window_start.strftime('%Y-%m-%d %H:%M:%S'),
        'predict_window_start': predict_window_start.strftime('%Y-%m-%d %H:%M:%S'),
        'trend': trend,
        'trend_code': int(prediction),
        'probability': prob,
        'predicted_change_rate': round(weighted_change_rate, 4),
        'predicted_hot_raw': predicted_hot_raw,
        'total_hot': feature['total_hot'],
        'total_hot_raw': total_hot_raw,
        'count': feature['count'],
        'message': 'success'
    }

@app.route('/api/predict/trend', methods=['GET'])
def predict_trend_api():
    """棰勬祴瓒嬪娍鐨凙PI鎺ュ彛

    Query Parameters:
        keyword: 鍏抽敭璇?
    Returns:
        JSON: 棰勬祴缁撴灉
    """
    keyword = request.args.get('keyword')

    if not keyword:
        return jsonify({
            'code': 400,
            'message': '鍏抽敭璇嶅弬鏁颁笉鑳戒负绌?,
            'data': None
        }), 400

    try:
        result = predict_trend(keyword)
        return jsonify({
            'code': 200,
            'message': 'success',
            'data': result
        })
    except Exception as e:
        logger.error(f"棰勬祴澶辫触: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'code': 500,
            'message': f'棰勬祴澶辫触: {str(e)}',
            'data': None
        }), 500

@app.route('/api/predict/trend/batch', methods=['POST'])
def predict_trend_batch_api():
    """鎵归噺棰勬祴瓒嬪娍鐨凙PI鎺ュ彛

    Request Body:
        JSON: {"keywords": ["鍏抽敭璇?", "鍏抽敭璇?", ...]}

    Returns:
        JSON: 鎵归噺棰勬祴缁撴灉
    """
    data = request.get_json()

    if not data or 'keywords' not in data:
        return jsonify({
            'code': 400,
            'message': '璇锋眰浣撳繀椤诲寘鍚玨eywords瀛楁',
            'data': None
        }), 400

    keywords = data['keywords']

    try:
        results = []
        for keyword in keywords:
            result = predict_trend(keyword)
            results.append(result)

        return jsonify({
            'code': 200,
            'message': 'success',
            'data': results
        })
    except Exception as e:
        logger.error(f"鎵归噺棰勬祴澶辫触: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'code': 500,
            'message': f'鎵归噺棰勬祴澶辫触: {str(e)}',
            'data': None
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """鍋ュ悍妫€鏌ユ帴鍙?""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

def main():
    """涓诲嚱鏁?""
    # 妯″瀷鏂囦欢鐩綍
    model_dir = r'e:\bishe\model_training'

    # 鍔犺浇妯″瀷
    load_models(model_dir)

    # 鍚姩Flask鏈嶅姟
    app.run(host='0.0.0.0', port=5000, debug=False)
    logger.info("瀹炴椂瓒嬪娍棰勬祴鏈嶅姟宸插惎鍔?)

if __name__ == '__main__':
    main()
