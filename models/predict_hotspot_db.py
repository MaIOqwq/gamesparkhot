#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XGBoost鐑偣鍒嗙被妯″瀷棰勬祴鑴氭湰锛堜娇鐢ㄦ暟鎹簱鏁版嵁锛?"""

import os
import sys
import time
import logging
import argparse
import pickle
import json
import pymysql
import numpy as np
import xgboost as xgb
from datetime import datetime, timedelta

# 閰嶇疆鏃ュ織
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_data_from_db(host, port, user, password, database, window_start):
    """浠庢暟鎹簱鍔犺浇鏁版嵁
    
    Args:
        host: 鏁版嵁搴撲富鏈?        port: 鏁版嵁搴撶鍙?        user: 鏁版嵁搴撶敤鎴峰悕
        password: 鏁版嵁搴撳瘑鐮?        database: 鏁版嵁搴撳悕绉?        window_start: 褰撳墠棰勬祴绐楀彛寮€濮嬫椂闂?        
    Returns:
        list: 鏁版嵁琛屽垪琛?    """
    logger.info("寮€濮嬩粠鏁版嵁搴撳姞杞芥暟鎹?..")
    
    # 璁＄畻鏃堕棿鑼冨洿锛氬綋鍓嶇獥鍙ｅ墠7澶╁埌褰撳墠绐楀彛鍚?灏忔椂
    start_time = window_start - timedelta(days=7)
    end_time = window_start + timedelta(hours=2)
    
    logger.info(f"鏁版嵁鏃堕棿鑼冨洿: {start_time} 鍒?{end_time}")
    
    try:
        # 杩炴帴鏁版嵁搴?        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        
        # 鏋勫缓SQL鏌ヨ
        query = f"""
            SELECT 
                keyword, publish_time, hot_score, like_count, comment_count, 
                view_count, coin_count, favorite_count, share_count, danmaku_count, 
                sentiment_score, author_fans, author_level, author_post_count, 
                has_image, has_video, platform
            FROM standardized_data
            WHERE publish_time >= '{start_time}' AND publish_time < '{end_time}'
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
        raise

def feature_engineering(rows, window_start, label_encoder):
    """鐗瑰緛宸ョ▼
    
    Args:
        rows: 鏁版嵁琛屽垪琛?        window_start: 褰撳墠棰勬祴绐楀彛寮€濮嬫椂闂?        label_encoder: LabelEncoder瀵硅薄
        
    Returns:
        list: 鐗瑰緛鍒楄〃
    """
    logger.info("寮€濮嬬壒寰佸伐绋?..")
    
    # 鎸夊叧閿瘝鍜岀獥鍙ｅ垎缁?    keyword_windows = {}
    for row in rows:
        # 璁＄畻绐楀彛鏃堕棿锛?灏忔椂绐楀彛锛?        pub_time = row['publish_time']
        window_hour = pub_time.hour - (pub_time.hour % 2)
        window_time = pub_time.replace(hour=window_hour, minute=0, second=0, microsecond=0)
        
        key = (row['keyword'], window_time)
        if key not in keyword_windows:
            keyword_windows[key] = []
        keyword_windows[key].append(row)
    
    # 璁＄畻鑱氬悎鐗瑰緛
    features = []
    for (keyword, window_time), window_rows in keyword_windows.items():
        # 鍙鐞嗗綋鍓嶇獥鍙ｇ殑鏁版嵁
        if window_time != window_start:
            continue
            
        # 璁＄畻鑱氬悎鐗瑰緛
        total_hot = sum(row['hot_score'] for row in window_rows)
        count = len(window_rows)
        avg_like = sum(row['like_count'] for row in window_rows) / count
        avg_comment = sum(row['comment_count'] for row in window_rows) / count
        avg_view = sum(row['view_count'] for row in window_rows) / count
        avg_coin = sum(row['coin_count'] for row in window_rows) / count
        avg_favorite = sum(row['favorite_count'] for row in window_rows) / count
        avg_share = sum(row['share_count'] for row in window_rows) / count
        avg_danmaku = sum(row['danmaku_count'] for row in window_rows) / count
        avg_sentiment = sum(row['sentiment_score'] for row in window_rows) / count
        avg_author_fans = sum(row['author_fans'] for row in window_rows) / count
        avg_author_level = sum(row['author_level'] for row in window_rows) / count
        avg_author_post_count = sum(row['author_post_count'] for row in window_rows) / count
        image_ratio = sum(row['has_image'] for row in window_rows) / count
        video_ratio = sum(row['has_video'] for row in window_rows) / count
        
        # 鏃堕棿鐗瑰緛
        hour = window_time.hour
        day_of_week = window_time.weekday() + 1  # 1-7
        is_weekend = 1 if day_of_week in (6, 7) else 0
        month = window_time.month
        
        # 鍏抽敭璇嶇紪鐮?        try:
            keyword_enc = label_encoder.transform([keyword])[0]
        except:
            keyword_enc = 0
        
        # 鏋勯€犵壒寰佸悜閲忥紙涓庤缁冩椂鐨勭壒寰侀『搴忎竴鑷达級
        feature = {
            'keyword_enc': keyword_enc,
            'total_hot': total_hot,
            'count': count,
            'avg_like': avg_like,
            'avg_comment': avg_comment,
            'avg_sentiment': avg_sentiment,
            'lag_1_total_hot': 0,  # 绠€鍖栧鐞嗭紝瀹為檯搴旇浠庡巻鍙叉暟鎹绠?            'lag_2_total_hot': 0,
            'lag_3_total_hot': 0,
            'lag_1_avg_like': 0,
            'lag_2_avg_like': 0,
            'lag_3_avg_like': 0,
            'lag_1_avg_comment': 0,
            'lag_2_avg_comment': 0,
            'lag_3_avg_comment': 0,
            'lag_1_avg_sentiment': 0,
            'lag_2_avg_sentiment': 0,
            'lag_3_avg_sentiment': 0,
            'total_hot_change_rate': 0,
            'rolling_mean_6_total_hot': total_hot,
            'rolling_std_6_total_hot': 0,
            'hour': hour,
            'day_of_week': day_of_week,
            'is_weekend': is_weekend,
            'month': month,
            'keyword': keyword
        }
        
        features.append(feature)
    
    logger.info(f"鐗瑰緛宸ョ▼瀹屾垚: 鍏?{len(features)} 鏉℃牱鏈?)
    return features

def main():
    """涓诲嚱鏁?""
    parser = argparse.ArgumentParser(description="XGBoost鐑偣鍒嗙被妯″瀷棰勬祴鑴氭湰")
    parser.add_argument("--model_path", default="./hotspot_classifier.json",
                      help="XGBoost妯″瀷璺緞")
    parser.add_argument("--feature_columns_path", default="./feature_columns.pkl",
                      help="鐗瑰緛鍒楀悕鏂囦欢璺緞")
    parser.add_argument("--label_encoder_path", default="./label_encoder.pkl",
                      help="LabelEncoder鏂囦欢璺緞")
    parser.add_argument("--output_dir", default="./predictions",
                      help="杈撳嚭鐩綍锛岀敤浜庝繚瀛楯SON缁撴灉")
    parser.add_argument("--db_host", default="<SERVER_IP>",
                      help="鏁版嵁搴撲富鏈?)
    parser.add_argument("--db_port", type=int, default=3306,
                      help="鏁版嵁搴撶鍙?)
    parser.add_argument("--db_user", default="spark",
                      help="鏁版嵁搴撶敤鎴峰悕")
    parser.add_argument("--db_password", default="123456",
                      help="鏁版嵁搴撳瘑鐮?)
    parser.add_argument("--db_name", default="standardized_data",
                      help="鏁版嵁搴撳悕绉?)
    
    args = parser.parse_args()
    
    logger.info("=======================================")
    logger.info("XGBoost鐑偣鍒嗙被妯″瀷棰勬祴寮€濮?)
    logger.info("=======================================")
    
    try:
        # 鍔犺浇妯″瀷
        logger.info("寮€濮嬪姞杞芥ā鍨?..")
        model = xgb.Booster()
        model.load_model(args.model_path)
        logger.info(f"妯″瀷鍔犺浇鎴愬姛: {args.model_path}")
        
        # 鍔犺浇鐗瑰緛鍒楀悕
        with open(args.feature_columns_path, 'rb') as f:
            feature_columns = pickle.load(f)
        logger.info(f"鐗瑰緛鍒楀悕鍔犺浇鎴愬姛: {args.feature_columns_path}")
        logger.info(f"鐗瑰緛鍒楁暟: {len(feature_columns)}")
        logger.info(f"鐗瑰緛鍒? {feature_columns[:5]}...")
        
        # 鍔犺浇LabelEncoder
        with open(args.label_encoder_path, 'rb') as f:
            label_encoder = pickle.load(f)
        logger.info(f"LabelEncoder鍔犺浇鎴愬姛: {args.label_encoder_path}")
        
        # 鑾峰彇褰撳墠绐楀彛锛?灏忔椂绐楀彛锛?        now = datetime.now()
        hours = now.hour - (now.hour % 2)
        window_start = now.replace(hour=hours, minute=0, second=0, microsecond=0)
        logger.info(f"褰撳墠棰勬祴绐楀彛: {window_start}")
        
        # 浠庢暟鎹簱鍔犺浇鏁版嵁
        rows = load_data_from_db(
            host=args.db_host,
            port=args.db_port,
            user=args.db_user,
            password=args.db_password,
            database=args.db_name,
            window_start=window_start
        )
        
        # 鐗瑰緛宸ョ▼
        features = feature_engineering(rows, window_start, label_encoder)
        
        # 妯″瀷棰勬祴
        logger.info("寮€濮嬫ā鍨嬮娴?..")
        predictions = []
        
        for feature in features:
            # 鍑嗗鐗瑰緛鐭╅樀
            feature_values = [feature[col] for col in feature_columns]
            feature_matrix = np.array([feature_values])
            
            # 杞崲涓篋Matrix锛屾寚瀹氱壒寰佸悕绉?            dmatrix = xgb.DMatrix(feature_matrix, feature_names=feature_columns)
            
            # 棰勬祴姒傜巼
            probability = model.predict(dmatrix)[0]
            is_hot = 1 if probability >= 0.45 else 0
            
            # 鐢熸垚棰勬祴缁撴灉
            predict_time = datetime.now()
            predictions.append({
                "keyword": feature['keyword'],
                "window_start": window_start.strftime("%Y-%m-%d %H:%M:%S"),
                "predict_time": predict_time.strftime("%Y-%m-%d %H:%M:%S"),
                "probability": float(probability),
                "is_hot": is_hot,
                "model_version": "v1.0"
            })
        
        # 杈撳嚭JSON缁撴灉鍒版湰鍦版枃浠?        if args.output_dir and predictions:
            os.makedirs(args.output_dir, exist_ok=True)
            output_file = os.path.join(args.output_dir, f"hotspot_predictions_{window_start.strftime('%Y%m%d_%H%M%S')}.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(predictions, f, ensure_ascii=False, indent=2)
            logger.info(f"棰勬祴缁撴灉宸蹭繚瀛樺埌: {output_file}")
        
        logger.info(f"棰勬祴瀹屾垚: 鍏?{len(predictions)} 鏉￠娴嬬粨鏋?)
        for pred in predictions:
            logger.info(f"鍏抽敭璇? {pred['keyword']}, 姒傜巼: {pred['probability']:.4f}, 鏄惁鐑偣: {pred['is_hot']}")
        
        logger.info("=======================================")
        logger.info("XGBoost鐑偣鍒嗙被妯″瀷棰勬祴缁撴潫")
        logger.info("=======================================")
        
        return 0
    except Exception as e:
        logger.error(f"棰勬祴娴佺▼澶辫触: {e}")
        import traceback
        traceback.print_exc()
        logger.info("=======================================")
        logger.info("XGBoost鐑偣鍒嗙被妯″瀷棰勬祴澶辫触")
        logger.info("=======================================")
        return 1

if __name__ == "__main__":
    sys.exit(main())