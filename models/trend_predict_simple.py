#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
绠€鍖栫増瀹炴椂瓒嬪娍棰勬祴 - 鐩存帴棰勬祴锛岃繑鍥炵粨鏋?"""

import os
import pickle
import json
import numpy as np
from datetime import datetime, timedelta
import pymysql

def load_models(model_dir):
    """鍔犺浇鎵€鏈夋ā鍨嬫枃浠?""
    model_path = os.path.join(model_dir, 'trend_classifier_2h.json')

    # 鍔犺浇XGBoost妯″瀷
    from xgboost import XGBClassifier
    model = XGBClassifier()
    model.load_model(model_path)

    # 鍔犺浇鐗瑰緛鍒楀悕
    with open(os.path.join(model_dir, 'trend_feature_columns_2h.pkl'), 'rb') as f:
        feature_columns = pickle.load(f)

    # 鍔犺浇LabelEncoder
    with open(os.path.join(model_dir, 'trend_label_encoder_2h.pkl'), 'rb') as f:
        label_encoder = pickle.load(f)

    # 鍔犺浇绫诲埆鏄犲皠
    with open(os.path.join(model_dir, 'trend_class_map_2h.pkl'), 'rb') as f:
        class_map = pickle.load(f)

    return model, feature_columns, label_encoder, class_map

def get_connection():
    return pymysql.connect(
        host='<SERVER_IP>',
        port=3306,
        user='spark',
        password = <DB_PASSWORD>,
        database='standardized_data',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def predict(keyword, model, feature_columns, label_encoder, class_map):
    """棰勬祴鎸囧畾鍏抽敭璇嶇殑2灏忔椂鍚庣儹搴﹁秼鍔?""

    # 鑾峰彇褰撳墠绐楀彛锛?灏忔椂绐楀彛锛?    now = datetime.now()
    hours = now.hour - (now.hour % 2)
    window_start = now.replace(hour=hours, minute=0, second=0, microsecond=0)

    # 璁＄畻鏃堕棿鑼冨洿锛氬綋鍓嶇獥鍙ｅ墠7澶╁埌褰撳墠绐楀彛鍚?灏忔椂
    start_time = window_start - timedelta(days=7)
    end_time = window_start + timedelta(hours=2)

    # 浠庢暟鎹簱鍔犺浇鏁版嵁
    conn = get_connection()
    query = f"""
        SELECT
            keyword, publish_time, hot_score, like_count, comment_count,
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

    if not rows:
        return {
            'keyword': keyword,
            'window_start': window_start.strftime('%Y-%m-%d %H:%M:%S'),
            'trend': '鏈煡',
            'trend_code': -1,
            'probability': 0.0,
            'message': '娌℃湁瓒冲鐨勬暟鎹繘琛岄娴?
        }

    # 鎸夌獥鍙ｅ垎缁勮仛鍚?    window_data = {}
    for row in rows:
        pub_time = row['publish_time']
        window_hour = pub_time.hour - (pub_time.hour % 2)
        window_time = pub_time.replace(hour=window_hour, minute=0, second=0, microsecond=0)

        if window_time not in window_data:
            window_data[window_time] = []
        window_data[window_time].append(row)

    sorted_windows = sorted(window_data.keys())
    current_idx = sorted_windows.index(window_start)

    current_window_data = window_data.get(window_start, [])

    # 璁＄畻鑱氬悎鐗瑰緛
    total_hot = sum(row['hot_score'] for row in current_window_data)
    count = len(current_window_data)
    avg_like = sum(row['like_count'] for row in current_window_data) / count
    avg_comment = sum(row['comment_count'] for row in current_window_data) / count
    avg_sentiment = sum(row['sentiment_score'] for row in current_window_data) / count

    # 鏃堕棿鐗瑰緛
    hour = window_start.hour
    day_of_week = window_start.weekday()
    is_weekend = 1 if day_of_week >= 5 else 0
    month = window_start.month

    # 鍏抽敭璇嶇紪鐮?    try:
        keyword_enc = label_encoder.transform([keyword])[0]
    except:
        keyword_enc = 0

    # 璁＄畻鍘嗗彶婊戝姩绐楀彛鐗瑰緛
    lag_features = {}
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

    lag_1_total_hot = lag_features.get('lag_1_total_hot', 0)
    total_hot_change_rate = (total_hot - lag_1_total_hot) / (lag_1_total_hot + 1e-6)

    # 璁＄畻婊氬姩鍧囧€煎拰鏍囧噯宸?    rolling_windows = sorted_windows[max(0, current_idx - 5):current_idx]
    if rolling_windows:
        rolling_total_hots = [sum(row['hot_score'] for row in window_data[sw]) for sw in rolling_windows]
        rolling_mean_6_total_hot = np.mean(rolling_total_hots) if rolling_total_hots else 0
        rolling_std_6_total_hot = np.std(rolling_total_hots) if rolling_total_hots else 0
    else:
        rolling_mean_6_total_hot = 0
        rolling_std_6_total_hot = 0

    # 鏋勯€犵壒寰佸悜閲?    feature = {
        'keyword_enc': keyword_enc,
        'total_hot': total_hot,
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

    # 棰勬祴
    feature_values = [feature[col] for col in feature_columns]
    feature_matrix = np.array([feature_values])

    prediction = model.predict(feature_matrix)[0]
    probability = model.predict_proba(feature_matrix)[0]

    trend = class_map.get(int(prediction), '鏈煡')
    prob = float(probability[int(prediction)])

    return {
        'keyword': keyword,
        'window_start': window_start.strftime('%Y-%m-%d %H:%M:%S'),
        'trend': trend,
        'trend_code': int(prediction),
        'probability': prob,
        'total_hot': total_hot,
        'count': count,
        'message': '棰勬祴鎴愬姛'
    }


if __name__ == '__main__':
    # 鍔犺浇妯″瀷
    model_dir = r'e:\bishe\model_training'
    model, feature_columns, label_encoder, class_map = load_models(model_dir)

    # 娴嬭瘯棰勬祴
    keyword = '鎵嬫満娓告垙'
    result = predict(keyword, model, feature_columns, label_encoder, class_map)
    print(json.dumps(result, ensure_ascii=False, indent=2))
