#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XGBoost鐑偣鍒嗙被妯″瀷棰勬祴鑴氭湰锛圥ySpark锛?
鍔熻兘锛氭瘡2灏忔椂棰勬祴涓€娆℃瘡涓叧閿瘝鍦ㄦ湭鏉?灏忔椂鏄惁鎴愪负鐑偣
鏁版嵁鏉ユ簮锛歁ariaDB鐨剆tandardized_data琛?棰勬祴缁撴灉锛氬啓鍏ariaDB鐨刪otspot_predictions琛?"""

import os
import sys
import time
import logging
import argparse
import pickle
import json
from datetime import datetime, timedelta

import numpy as np
import xgboost as xgb
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, hour, dayofweek, month, when, sum, mean, count, lag, floor, from_unixtime, udf, sqrt, pow
from pyspark.sql.window import Window
from pyspark.sql.types import DoubleType, IntegerType, FloatType, TimestampType

# 閰嶇疆鏃ュ織
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('predict_hotspot.log')
    ]
)
logger = logging.getLogger(__name__)

class HotspotPredictor:
    def __init__(self, spark, model_path, feature_columns_path, label_encoder_path, db_config):
        """鍒濆鍖栭娴嬪櫒
        
        Args:
            spark: SparkSession瀹炰緥
            model_path: XGBoost妯″瀷璺緞
            feature_columns_path: 鐗瑰緛鍒楀悕鏂囦欢璺緞
            label_encoder_path: LabelEncoder鏂囦欢璺緞
            db_config: 鏁版嵁搴撻厤缃?        """
        self.spark = spark
        self.model_path = model_path
        self.feature_columns_path = feature_columns_path
        self.label_encoder_path = label_encoder_path
        self.db_config = db_config
        self.threshold = 0.45  # 鐑偣闃堝€?        self.model = None
        self.feature_columns = None
        self.label_encoder = None
    
    def load_model(self):
        """鍔犺浇妯″瀷鍜岀浉鍏虫枃浠?""
        logger.info("寮€濮嬪姞杞芥ā鍨嬪拰鐩稿叧鏂囦欢...")
        
        # 鍔犺浇XGBoost妯″瀷
        try:
            self.model = xgb.Booster()
            self.model.load_model(self.model_path)
            logger.info(f"妯″瀷鍔犺浇鎴愬姛: {self.model_path}")
        except Exception as e:
            logger.error(f"妯″瀷鍔犺浇澶辫触: {e}")
            raise
        
        # 鍔犺浇鐗瑰緛鍒楀悕
        try:
            with open(self.feature_columns_path, 'rb') as f:
                self.feature_columns = pickle.load(f)
            logger.info(f"鐗瑰緛鍒楀悕鍔犺浇鎴愬姛: {self.feature_columns_path}")
        except Exception as e:
            logger.error(f"鐗瑰緛鍒楀悕鍔犺浇澶辫触: {e}")
            raise
        
        # 鍔犺浇LabelEncoder
        try:
            with open(self.label_encoder_path, 'rb') as f:
                self.label_encoder = pickle.load(f)
            logger.info(f"LabelEncoder鍔犺浇鎴愬姛: {self.label_encoder_path}")
        except Exception as e:
            logger.error(f"LabelEncoder鍔犺浇澶辫触: {e}")
            raise
    
    def get_current_window(self):
        """鑾峰彇褰撳墠棰勬祴绐楀彛
        
        Returns:
            window_start: 褰撳墠绐楀彛璧峰鏃堕棿
        """
        now = datetime.now()
        # 鍚戜笅鍙栨暣鍒?灏忔椂
        hours = now.hour - (now.hour % 2)
        window_start = now.replace(hour=hours, minute=0, second=0, microsecond=0)
        logger.info(f"褰撳墠棰勬祴绐楀彛: {window_start}")
        return window_start
    
    def load_data(self, window_start):
        """浠庢暟鎹簱鍔犺浇鏁版嵁
        
        Args:
            window_start: 褰撳墠绐楀彛璧峰鏃堕棿
            
        Returns:
            df: 鍔犺浇鐨勬暟鎹?        """
        logger.info("寮€濮嬩粠鏁版嵁搴撳姞杞芥暟鎹?..")
        
        # 璁＄畻鏃堕棿鑼冨洿
        start_time = window_start - timedelta(days=7)
        end_time = window_start + timedelta(hours=2)
        
        logger.info(f"鏁版嵁鏃堕棿鑼冨洿: {start_time} 鍒?{end_time}")
        
        try:
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
            
            df = self.spark.read.format("jdbc") \
                .option("url", self.db_config["url"]) \
                .option("driver", self.db_config["driver"]) \
                .option("query", query) \
                .option("user", self.db_config["user"]) \
                .option("password", self.db_config["password"]) \
                .load()
            
            logger.info(f"鏁版嵁鍔犺浇瀹屾垚: 鍏?{df.count()} 鏉¤褰?)
            return df
        except Exception as e:
            logger.error(f"鏁版嵁鍔犺浇澶辫触: {e}")
            raise
    
    def encode_keyword(self, keyword):
        """缂栫爜鍏抽敭璇?        
        Args:
            keyword: 鍏抽敭璇?            
        Returns:
            缂栫爜鍚庣殑鏁板€?        """
        try:
            return self.label_encoder.transform([keyword])[0]
        except:
            return 0  # 瀵逛簬鏈杩囩殑鍏抽敭璇嶏紝杩斿洖0
    
    def feature_engineering(self, df, window_start):
        """鐗瑰緛宸ョ▼
        
        Args:
            df: 鍘熷鏁版嵁
            window_start: 褰撳墠绐楀彛璧峰鏃堕棿
            
        Returns:
            feature_df: 鐗瑰緛鏁版嵁
        """
        logger.info("寮€濮嬬壒寰佸伐绋?..")
        
        # 鏋勯€爓indow_start锛坧ublish_time鍚戜笅鍙栨暣鍒?灏忔椂锛?        df = df.withColumn("window_start", 
            floor(col("publish_time").cast("long") / (2 * 3600)) * (2 * 3600)
        )
        df = df.withColumn("window_start", from_unixtime(col("window_start")))
        
        # 鎸?keyword, window_start)鍒嗙粍鑱氬悎
        aggregated = df.groupBy("keyword", "window_start").agg(
            sum("hot_score").alias("total_hot"),
            count("*").alias("count"),
            mean("like_count").alias("avg_like"),
            mean("comment_count").alias("avg_comment"),
            mean("view_count").alias("avg_view"),
            mean("coin_count").alias("avg_coin"),
            mean("favorite_count").alias("avg_favorite"),
            mean("share_count").alias("avg_share"),
            mean("danmaku_count").alias("avg_danmaku"),
            mean("sentiment_score").alias("avg_sentiment"),
            mean("author_fans").alias("avg_author_fans"),
            mean("author_level").alias("avg_author_level"),
            mean("author_post_count").alias("avg_author_post_count"),
            mean("has_image").alias("image_ratio"),
            mean("has_video").alias("video_ratio")
        )
        
        # 鏃堕棿鐗瑰緛
        aggregated = aggregated.withColumn("hour", hour(col("window_start")))
        aggregated = aggregated.withColumn("day_of_week", dayofweek(col("window_start")))
        aggregated = aggregated.withColumn("is_weekend", when(col("day_of_week").isin(6, 7), 1).otherwise(0))
        aggregated = aggregated.withColumn("month", month(col("window_start")))
        
        # 鍘嗗彶婊戝姩绐楀彛鐗瑰緛
        window_spec = Window.partitionBy("keyword").orderBy("window_start")
        
        # 鐢熸垚lag鐗瑰緛
        features_to_lag = ['total_hot', 'avg_like', 'avg_comment', 'avg_sentiment', 'count']
        for feature in features_to_lag:
            for i in range(1, 4):
                aggregated = aggregated.withColumn(f'lag_{i}_{feature}', 
                    lag(col(feature), i).over(window_spec)
                )
        
        # 璁＄畻鐑害鍙樺寲鐜?        aggregated = aggregated.withColumn("total_hot_change_rate", 
            (col("total_hot") - col("lag_1_total_hot")) / (col("lag_1_total_hot") + 1e-6)
        )
        
        # 璁＄畻婊氬姩鍧囧€煎拰鏍囧噯宸?        window_spec_roll = Window.partitionBy("keyword").orderBy("window_start").rowsBetween(-5, 0)
        aggregated = aggregated.withColumn("rolling_mean_6_total_hot", 
            mean(col("total_hot").cast(DoubleType())).over(window_spec_roll)
        )
        
        # 璁＄畻鏍囧噯宸紙Spark SQL娌℃湁鍐呯疆鐨勬爣鍑嗗樊绐楀彛鍑芥暟锛岃繖閲屼娇鐢ㄨ繎浼煎€硷級
        aggregated = aggregated.withColumn("rolling_std_6_total_hot", 
            sqrt(mean(pow(col("total_hot").cast(DoubleType()) - col("rolling_mean_6_total_hot"), 2)).over(window_spec_roll)
        )
        
        # 缂哄け鍊煎～鍏呬负0
        aggregated = aggregated.fillna(0)
        
        # 鍙繚鐣欏綋鍓嶉娴嬬獥鍙?        feature_df = aggregated.filter(col("window_start") == window_start)
        
        logger.info(f"鐗瑰緛宸ョ▼瀹屾垚: 鍏?{feature_df.count()} 鏉℃牱鏈?)
        return feature_df
    
    def predict(self, feature_df, window_start):
        """妯″瀷棰勬祴
        
        Args:
            feature_df: 鐗瑰緛鏁版嵁
            window_start: 褰撳墠绐楀彛璧峰鏃堕棿
            
        Returns:
            tuple: (prediction_df, predictions)
        """
        logger.info("寮€濮嬫ā鍨嬮娴?..")
        
        if feature_df.count() == 0:
            logger.info("娌℃湁鏍锋湰闇€瑕侀娴?)
            return None, []
        
        # 鍑嗗鐗瑰緛鐭╅樀
        feature_data = feature_df.select(self.feature_columns).collect()
        feature_matrix = np.array([row.asDict().values() for row in feature_data])
        
        # 杞崲涓篋Matrix
        dmatrix = xgb.DMatrix(feature_matrix)
        
        # 棰勬祴姒傜巼
        probabilities = self.model.predict(dmatrix)
        
        # 鐢熸垚棰勬祴缁撴灉
        predict_time = datetime.now()
        predictions = []
        keywords = feature_df.select("keyword").collect()
        
        for i, prob in enumerate(probabilities):
            keyword = keywords[i][0]
            is_hot = 1 if prob >= self.threshold else 0
            predictions.append({
                "keyword": keyword,
                "window_start": window_start.strftime("%Y-%m-%d %H:%M:%S"),
                "predict_time": predict_time.strftime("%Y-%m-%d %H:%M:%S"),
                "probability": float(prob),
                "is_hot": is_hot,
                "model_version": "v1.0"
            })
        
        # 鍒涘缓棰勬祴缁撴灉DataFrame
        prediction_df = self.spark.createDataFrame(predictions)
        
        logger.info(f"棰勬祴瀹屾垚: 鍏?{prediction_df.count()} 鏉￠娴嬬粨鏋?)
        return prediction_df, predictions
    
    def write_results(self, prediction_df):
        """鍐欏叆棰勬祴缁撴灉鍒版暟鎹簱
        
        Args:
            prediction_df: 棰勬祴缁撴灉
        """
        if prediction_df is None:
            logger.info("娌℃湁棰勬祴缁撴灉闇€瑕佸啓鍏?)
            return
        
        logger.info("寮€濮嬪啓鍏ラ娴嬬粨鏋?..")
        
        try:
            prediction_df.write.format("jdbc") \
                .option("url", self.db_config["url"]) \
                .option("driver", self.db_config["driver"]) \
                .option("dbtable", "hotspot_predictions") \
                .option("user", self.db_config["user"]) \
                .option("password", self.db_config["password"]) \
                .mode("append") \
                .save()
            
            logger.info(f"棰勬祴缁撴灉鍐欏叆鎴愬姛: 鍏?{prediction_df.count()} 鏉¤褰?)
        except Exception as e:
            logger.error(f"棰勬祴缁撴灉鍐欏叆澶辫触: {e}")
            raise
    
    def run(self, output_dir=None):
        """鎵ц瀹屾暣鐨勯娴嬫祦绋?        
        Args:
            output_dir: 杈撳嚭鐩綍锛岀敤浜庝繚瀛楯SON缁撴灉
        """
        start_time = time.time()
        logger.info("=======================================")
        logger.info("XGBoost鐑偣鍒嗙被妯″瀷棰勬祴寮€濮?)
        logger.info("=======================================")
        
        try:
            # 鍔犺浇妯″瀷
            self.load_model()
            
            # 鑾峰彇褰撳墠绐楀彛
            window_start = self.get_current_window()
            
            # 鍔犺浇鏁版嵁
            df = self.load_data(window_start)
            
            # 鐗瑰緛宸ョ▼
            feature_df = self.feature_engineering(df, window_start)
            
            # 妯″瀷棰勬祴
            prediction_df, predictions = self.predict(feature_df, window_start)
            
            # 鍐欏叆缁撴灉鍒版暟鎹簱
            self.write_results(prediction_df)
            
            # 杈撳嚭JSON缁撴灉鍒版湰鍦版枃浠?            if output_dir and predictions:
                os.makedirs(output_dir, exist_ok=True)
                output_file = os.path.join(output_dir, f"hotspot_predictions_{window_start.strftime('%Y%m%d_%H%M%S')}.json")
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(predictions, f, ensure_ascii=False, indent=2)
                logger.info(f"棰勬祴缁撴灉宸蹭繚瀛樺埌: {output_file}")
            
            end_time = time.time()
            logger.info(f"棰勬祴娴佺▼瀹屾垚锛岃€楁椂: {end_time - start_time:.2f}绉?)
            logger.info("=======================================")
            logger.info("XGBoost鐑偣鍒嗙被妯″瀷棰勬祴缁撴潫")
            logger.info("=======================================")
            
            return 0
        except Exception as e:
            logger.error(f"棰勬祴娴佺▼澶辫触: {e}")
            logger.info("=======================================")
            logger.info("XGBoost鐑偣鍒嗙被妯″瀷棰勬祴澶辫触")
            logger.info("=======================================")
            return 1

def main():
    """涓诲嚱鏁?""
    parser = argparse.ArgumentParser(description="XGBoost鐑偣鍒嗙被妯″瀷棰勬祴鑴氭湰")
    parser.add_argument("--model_path", default="/opt/models/hotspot_classifier.json",
                      help="XGBoost妯″瀷璺緞")
    parser.add_argument("--feature_columns_path", default="/opt/models/feature_columns.pkl",
                      help="鐗瑰緛鍒楀悕鏂囦欢璺緞")
    parser.add_argument("--label_encoder_path", default="/opt/models/label_encoder.pkl",
                      help="LabelEncoder鏂囦欢璺緞")
    parser.add_argument("--db_host", default="<SERVER_IP>",
                      help="鏁版嵁搴撲富鏈?)
    parser.add_argument("--db_port", default="3306",
                      help="鏁版嵁搴撶鍙?)
    parser.add_argument("--db_user", default="spark",
                      help="鏁版嵁搴撶敤鎴峰悕")
    parser.add_argument("--db_password", default="123456",
                      help="鏁版嵁搴撳瘑鐮?)
    parser.add_argument("--db_name", default="standardized_data",
                      help="鏁版嵁搴撳悕绉?)
    parser.add_argument("--output_dir", default=None,
                      help="杈撳嚭鐩綍锛岀敤浜庝繚瀛楯SON缁撴灉")
    
    args = parser.parse_args()
    
    # 鍒涘缓SparkSession
    spark = SparkSession.builder \
        .appName("HotspotPredictor") \
        .master("local[2]") \
        .getOrCreate()
    
    # 鏁版嵁搴撻厤缃?    db_config = {
        "url": f"jdbc:mariadb://{args.db_host}:{args.db_port}/{args.db_name}",
        "driver": "org.mariadb.jdbc.Driver",
        "user": args.db_user,
        "password": args.db_password
    }
    
    # 鍒涘缓棰勬祴鍣?    predictor = HotspotPredictor(
        spark=spark,
        model_path=args.model_path,
        feature_columns_path=args.feature_columns_path,
        label_encoder_path=args.label_encoder_path,
        db_config=db_config
    )
    
    # 鎵ц棰勬祴
    exit_code = predictor.run(output_dir=args.output_dir)
    
    # 鍏抽棴SparkSession
    spark.stop()
    
    return exit_code

if __name__ == "__main__":
    sys.exit(main())