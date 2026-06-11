import pandas as pd
import numpy as np
import pymysql
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import xgboost as xgb
import joblib
import logging
from datetime import datetime, timedelta

# 璁剧疆鏃ュ織
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('model_training/training.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class XGBoostHotnessTrainer:
    def __init__(self):
        self.db_config = {
            'host': '<SERVER_IP>',
            'port': 3306,
            'database': 'standardized_data',
            'username': 'spark',
            'password': '123456',
            'table_name': 'standardized_data'
        }
        self.df = None
        self.aggregated_df = None
        self.processed_df = None
        self.label_encoder = None
        self.model = None
        self.feature_names = None
    
    def connect_database(self):
        """杩炴帴MariaDB鏁版嵁搴撳苟璇诲彇鏁版嵁"""
        try:
            logger.info("姝ｅ湪杩炴帴鏁版嵁搴?..")
            connection = pymysql.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                user=self.db_config['username'],
                password=self.db_config['password'],
                database=self.db_config['database'],
                charset='utf8mb4'
            )
            
            query = f"""
            SELECT keyword, hot_score, like_count, comment_count, view_count, 
                   coin_count, favorite_count, share_count, publish_time
            FROM {self.db_config['table_name']}
            WHERE publish_time >= '2020-01-01'
            """
            
            self.df = pd.read_sql(query, connection)
            connection.close()
            
            logger.info(f"鎴愬姛璇诲彇鏁版嵁锛屽叡 {len(self.df)} 鏉¤褰?)
            return True
            
        except Exception as e:
            logger.error(f"鏁版嵁搴撹繛鎺ュけ璐? {str(e)}")
            logger.info("浣跨敤绀轰緥鏁版嵁缁х画璁粌...")
            self.generate_sample_data()
            return False
    
    def generate_sample_data(self):
        """鐢熸垚绀轰緥鏁版嵁鐢ㄤ簬娴嬭瘯"""
        logger.info("鐢熸垚绀轰緥鏁版嵁...")
        np.random.seed(42)
        
        keywords = ['鎶€鏈?, '濞变箰', '浣撹偛', '璐㈢粡', '鏁欒偛']
        start_date = pd.Timestamp('2020-01-01')
        end_date = pd.Timestamp('2026-03-31')
        
        data = []
        for i in range(10000):
            keyword = np.random.choice(keywords)
            publish_time = start_date + timedelta(days=np.random.randint(0, 2300))
            hot_score = np.random.uniform(0, 1)
            like_count = np.random.randint(0, 1000)
            comment_count = np.random.randint(0, 500)
            view_count = np.random.randint(0, 10000)
            coin_count = np.random.randint(0, 200)
            favorite_count = np.random.randint(0, 300)
            share_count = np.random.randint(0, 100)
            
            data.append([keyword, hot_score, like_count, comment_count, view_count,
                        coin_count, favorite_count, share_count, publish_time])
        
        self.df = pd.DataFrame(data, columns=[
            'keyword', 'hot_score', 'like_count', 'comment_count', 'view_count',
            'coin_count', 'favorite_count', 'share_count', 'publish_time'
        ])
        logger.info(f"鐢熸垚浜?{len(self.df)} 鏉＄ず渚嬫暟鎹?)
    
    def preprocess_data(self):
        """鏁版嵁棰勫鐞?""
        logger.info("寮€濮嬫暟鎹澶勭悊...")
        
        # 灏唒ublish_time杞崲涓篸atetime绫诲瀷
        self.df['publish_time'] = pd.to_datetime(self.df['publish_time'])
        logger.info(f"鏁版嵁鏃堕棿鑼冨洿: {self.df['publish_time'].min()} 鑷?{self.df['publish_time'].max()}")
        
        # 杩囨护鎺夊紓甯稿€?        self.df = self.df[(self.df['hot_score'] >= 0) & (self.df['hot_score'] <= 1)]
        logger.info(f"杩囨护鍚庢暟鎹噺: {len(self.df)}")
    
    def create_time_windows(self):
        """鍒涘缓2灏忔椂鏃堕棿绐楀彛骞惰仛鍚堟暟鎹紝濉厖鏃犳暟鎹獥鍙ｄ负0"""
        logger.info("鍒涘缓2灏忔椂鏃堕棿绐楀彛...")
        
        # 鍒涘缓2灏忔椂绐楀彛
        self.df['window_start'] = self.df['publish_time'].dt.floor('2H')
        
        # 鎸塳eyword鍜寃indow_start鍒嗙粍鑱氬悎
        agg_dict = {
            'hot_score': 'sum',
            'like_count': 'mean',
            'comment_count': 'mean',
            'view_count': 'mean',
            'coin_count': 'mean',
            'favorite_count': 'mean',
            'share_count': 'mean',
            'publish_time': 'count'
        }
        
        aggregated_df = self.df.groupby(['keyword', 'window_start']).agg(agg_dict).reset_index()
        aggregated_df.columns = ['keyword', 'window_start', 'total_hot', 
                                'avg_like', 'avg_comment', 'avg_view', 
                                'avg_coin', 'avg_favorite', 'avg_share', 'count']
        
        # 鐢熸垚瀹屾暣鐨勬椂闂寸獥鍙ｅ苟濉厖鏃犳暟鎹獥鍙ｄ负0
        logger.info("鐢熸垚瀹屾暣鐨勬椂闂寸獥鍙ｅ苟濉厖鏃犳暟鎹獥鍙?..")
        
        # 涓烘瘡涓叧閿瘝鍗曠嫭鍒涘缓鍏舵椂闂磋寖鍥村唴鐨勭獥鍙?        full_df_list = []
        all_keywords = self.df['keyword'].unique()
        
        for keyword in all_keywords:
            keyword_data = self.df[self.df['keyword'] == keyword]
            min_time = keyword_data['window_start'].min()
            max_time = keyword_data['window_start'].max()
            
            # 鍒涘缓璇ュ叧閿瘝鏃堕棿鑼冨洿鍐呯殑鎵€鏈?灏忔椂绐楀彛
            all_windows = pd.date_range(start=min_time, end=max_time, freq='2H')
            keyword_df = pd.DataFrame({
                'keyword': keyword,
                'window_start': all_windows
            })
            full_df_list.append(keyword_df)
        
        full_df = pd.concat(full_df_list)
        
        # 鍚堝苟瀹為檯鏁版嵁
        self.aggregated_df = full_df.merge(aggregated_df, 
                                         on=['keyword', 'window_start'], 
                                         how='left')
        
        # 濉厖缂哄け鍊间负0
        fill_columns = ['total_hot', 'avg_like', 'avg_comment', 'avg_view', 
                       'avg_coin', 'avg_favorite', 'avg_share', 'count']
        self.aggregated_df[fill_columns] = self.aggregated_df[fill_columns].fillna(0)
        
        # 杈撳嚭姣忎釜鍏抽敭璇嶇殑绐楀彛鏁伴噺
        keyword_window_counts = self.aggregated_df.groupby('keyword').size().sort_values(ascending=False)
        logger.info("姣忎釜鍏抽敭璇嶇殑绐楀彛鏁伴噺:")
        for keyword, count in keyword_window_counts.items():
            logger.info(f"  {keyword}: {count}")
        
        logger.info(f"鑱氬悎鍚庢暟鎹噺锛堝惈濉厖绐楀彛锛? {len(self.aggregated_df)}")
    
    def extract_time_features(self):
        """鎻愬彇鏃堕棿鐗瑰緛"""
        logger.info("鎻愬彇鏃堕棿鐗瑰緛...")
        
        df = self.aggregated_df
        df['hour'] = df['window_start'].dt.hour
        df['day_of_week'] = df['window_start'].dt.dayofweek
        df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
        df['month'] = df['window_start'].dt.month
        
        self.processed_df = df
    
    def create_sliding_window_features(self):
        """鍒涘缓鍘嗗彶婊戝姩绐楀彛鐗瑰緛"""
        logger.info("鍒涘缓鍘嗗彶婊戝姩绐楀彛鐗瑰緛...")
        
        df = self.processed_df.sort_values(['keyword', 'window_start'])
        
        # 瀵规瘡涓猭eyword鍗曠嫭澶勭悊
        df['lag_1_total_hot'] = df.groupby('keyword')['total_hot'].shift(1)
        df['lag_2_total_hot'] = df.groupby('keyword')['total_hot'].shift(2)
        df['lag_3_total_hot'] = df.groupby('keyword')['total_hot'].shift(3)
        # 澧炲姞鏇撮暱鍛ㄦ湡鐨勬粸鍚庣壒寰?        df['lag_6_total_hot'] = df.groupby('keyword')['total_hot'].shift(6)
        
        # 璁＄畻杩囧幓2涓獥鍙ｇ殑鐑害鎬诲拰锛堣繃鍘?灏忔椂锛?        df['sum_lag_2_total_hot'] = df.groupby('keyword')['total_hot'].rolling(window=2).sum().shift(1).reset_index(level=0, drop=True)
        
        # 璁＄畻杩囧幓3涓獥鍙ｇ殑鐑害鎬诲拰锛堣繃鍘?灏忔椂锛?        df['sum_lag_3_total_hot'] = df.groupby('keyword')['total_hot'].rolling(window=3).sum().shift(1).reset_index(level=0, drop=True)
        
        # 璁＄畻鐑害鍙樺寲鐜?        df['hot_change_rate'] = (df['total_hot'] - df['lag_1_total_hot']) / (df['lag_1_total_hot'] + 1e-6)
        
        # 杩囧幓1涓獥鍙ｇ殑骞冲潎璇勮鏁板拰鐐硅禐鏁?        df['lag_1_avg_comment'] = df.groupby('keyword')['avg_comment'].shift(1)
        df['lag_1_avg_like'] = df.groupby('keyword')['avg_like'].shift(1)
        
        # 澧炲姞浜掑姩鍙樺寲鐜囩壒寰?        df['like_change_rate'] = (df['avg_like'] - df['lag_1_avg_like']) / (df['lag_1_avg_like'] + 1e-6)
        df['comment_change_rate'] = (df['avg_comment'] - df['lag_1_avg_comment']) / (df['lag_1_avg_comment'] + 1e-6)
        
        # 澧炲姞澶氭椂闂村昂搴︽粦鍔ㄧ獥鍙ｇ壒寰?        # 杩囧幓6涓獥鍙ｇ殑鐑害鍧囧€硷紙杩囧幓12灏忔椂锛?        df['total_hot_rolling_mean_6'] = df.groupby('keyword')['total_hot'].rolling(window=6, min_periods=1).mean().shift(1).reset_index(level=0, drop=True)
        
        # 杩囧幓6涓獥鍙ｇ殑鐑害鏍囧噯宸紙鍙嶆槧娉㈠姩锛?        df['total_hot_rolling_std_6'] = df.groupby('keyword')['total_hot'].rolling(window=6, min_periods=1).std().shift(1).reset_index(level=0, drop=True)
        
        # 杩囧幓12涓獥鍙ｇ殑鏈€澶х儹搴︼紙杩囧幓24灏忔椂宄板€硷級
        df['total_hot_rolling_max_12'] = df.groupby('keyword')['total_hot'].rolling(window=12, min_periods=1).max().shift(1).reset_index(level=0, drop=True)
        
        self.processed_df = df
    
    def create_labels(self):
        """鏋勯€犳湭鏉?灏忔椂鐑害鏍囩"""
        logger.info("鏋勯€犳湭鏉?灏忔椂鐑害鏍囩...")
        
        df = self.processed_df.sort_values(['keyword', 'window_start'])
        
        # 鏈潵6灏忔椂瀵瑰簲3涓獥鍙ｏ紙姣忎釜绐楀彛2灏忔椂锛?        df['label_6h'] = df.groupby('keyword')['total_hot'].shift(-3)
        
        self.processed_df = df
    
    def clean_data(self):
        """鏁版嵁娓呮礂涓庤繃婊?""
        logger.info("鏁版嵁娓呮礂涓嶥ouble-check...")
        
        df = self.processed_df
        
        # 涓㈠純鍖呭惈NaN鐨勮
        initial_count = len(df)
        df = df.dropna()
        logger.info(f"涓㈠純NaN鍚庢暟鎹噺: {len(df)} (鍑忓皯 {initial_count - len(df)} 琛?")
        
        # 杩囨护鎺夋牱鏈暟杩囧皯鐨勫叧閿瘝锛堝皯浜?0涓獥鍙ｏ級
        keyword_counts = df['keyword'].value_counts()
        valid_keywords = keyword_counts[keyword_counts >= 50].index.tolist()
        df = df[df['keyword'].isin(valid_keywords)]
        logger.info(f"杩囨护鍚庡叧閿瘝鏁伴噺: {len(valid_keywords)}")
        logger.info(f"杩囨护鍚庢暟鎹噺: {len(df)}")
        
        # 纭繚鎵€鏈夋暟鍊煎垪鍧囦负鏁板€肩被鍨?        numeric_cols = ['total_hot', 'avg_like', 'avg_comment', 'avg_view', 'avg_coin', 
                       'avg_favorite', 'avg_share', 'count', 'hour', 'day_of_week', 
                       'is_weekend', 'month', 'lag_1_total_hot', 'lag_2_total_hot', 
                       'lag_3_total_hot', 'lag_6_total_hot', 'sum_lag_2_total_hot', 
                       'sum_lag_3_total_hot', 'hot_change_rate', 'lag_1_avg_comment', 
                       'lag_1_avg_like', 'like_change_rate', 'comment_change_rate', 
                       'total_hot_rolling_mean_6', 'total_hot_rolling_std_6', 
                       'total_hot_rolling_max_12', 'label_6h']
        
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        self.processed_df = df
    
    def encode_keywords(self):
        """瀵瑰叧閿瘝杩涜鏍囩缂栫爜"""
        logger.info("瀵瑰叧閿瘝杩涜鏍囩缂栫爜...")
        
        self.label_encoder = LabelEncoder()
        self.processed_df['keyword_encoded'] = self.label_encoder.fit_transform(self.processed_df['keyword'])
        
        # 淇濆瓨鏍囩缂栫爜鍣?        joblib.dump(self.label_encoder, 'model_training/label_encoder.pkl')
        logger.info(f"缂栫爜浜?{len(self.label_encoder.classes_)} 涓叧閿瘝")
    
    def split_data(self):
        """鎸夋椂闂撮『搴忓垝鍒嗘暟鎹?""
        logger.info("鎸夋椂闂撮『搴忓垝鍒嗘暟鎹?..")
        
        df = self.processed_df
        
        # 璁粌闆嗭細2020-01-01 鑷?2024-12-31
        train_mask = (df['window_start'] >= pd.Timestamp('2020-01-01')) & \
                    (df['window_start'] <= pd.Timestamp('2024-12-31'))
        
        # 楠岃瘉闆嗭細2025-01-01 鑷?2025-12-31
        val_mask = (df['window_start'] >= pd.Timestamp('2025-01-01')) & \
                  (df['window_start'] <= pd.Timestamp('2025-12-31'))
        
        # 娴嬭瘯闆嗭細2026-01-01 鑷?褰撳墠鏃ユ湡
        test_mask = (df['window_start'] >= pd.Timestamp('2026-01-01'))
        
        X_train = df[train_mask].copy()
        X_val = df[val_mask].copy()
        X_test = df[test_mask].copy()
        
        y_train = X_train['label_6h']
        y_val = X_val['label_6h']
        y_test = X_test['label_6h']
        
        logger.info(f"璁粌闆嗗ぇ灏? {len(X_train)}")
        logger.info(f"楠岃瘉闆嗗ぇ灏? {len(X_val)}")
        logger.info(f"娴嬭瘯闆嗗ぇ灏? {len(X_test)}")
        
        return X_train, X_val, X_test, y_train, y_val, y_test
    
    def prepare_features(self, X):
        """鍑嗗鐗瑰緛鍒?""
        # 鐗瑰緛鍒楋細鎺掗櫎keyword鍘熷鍒椼€亀indow_start銆乴abel_6h
        feature_cols = [col for col in X.columns if col not in ['keyword', 'window_start', 'label_6h']]
        self.feature_names = feature_cols
        
        # 淇濆瓨鐗瑰緛鍚嶇О鍒楄〃
        joblib.dump(feature_cols, 'model_training/feature_names.pkl')
        
        return X[feature_cols]
    
    def train_model(self, X_train, y_train, X_val, y_val):
        """璁粌XGBoost鍥炲綊妯″瀷"""
        logger.info("寮€濮嬭缁僗GBoost妯″瀷...")
        
        # 鍑嗗鐗瑰緛
        X_train_features = self.prepare_features(X_train)
        X_val_features = self.prepare_features(X_val)
        
        # 璁剧疆妯″瀷鍙傛暟
        params = {
            'objective': 'reg:squarederror',
            'eval_metric': 'rmse',
            'max_depth': 5,
            'learning_rate': 0.02,
            'n_estimators': 2000,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'reg_lambda': 2.0,
            'reg_alpha': 0.5,
            'random_state': 42,
            'verbosity': 1
        }
        
        # 鍒涘缓XGBoost鍥炲綊鍣?        self.model = xgb.XGBRegressor(**params)
        
        # 浣跨敤鏃╁仠娉曡缁冩ā鍨?        self.model.fit(
            X_train_features, y_train,
            eval_set=[(X_val_features, y_val)],
            early_stopping_rounds=20,
            verbose=True
        )
        
        logger.info("妯″瀷璁粌瀹屾垚")
    
    def evaluate_model(self, X_test, y_test):
        """璇勪及妯″瀷鎬ц兘"""
        logger.info("寮€濮嬭瘎浼版ā鍨嬫€ц兘...")
        
        X_test_features = self.prepare_features(X_test)
        y_pred = self.model.predict(X_test_features)
        
        # 璁＄畻璇勪及鎸囨爣
        mse = mean_squared_error(y_test, y_pred)
        rmse = np.sqrt(mse)
        mae = mean_absolute_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)
        
        logger.info(f"妯″瀷璇勪及缁撴灉:")
        logger.info(f"  MSE: {mse:.6f}")
        logger.info(f"  RMSE: {rmse:.6f}")
        logger.info(f"  MAE: {mae:.6f}")
        logger.info(f"  R虏: {r2:.6f}")
        
        return {'mse': mse, 'rmse': rmse, 'mae': mae, 'r2': r2}
    
    def save_model(self):
        """淇濆瓨妯″瀷鍜岀浉鍏虫枃浠?""
        logger.info("淇濆瓨妯″瀷鏂囦欢...")
        
        # 淇濆瓨妯″瀷涓篔SON鏍煎紡
        self.model.get_booster().save_model('model_training/hotness_keyword_model.json')
        
        # 淇濆瓨妯″瀷瀵硅薄
        joblib.dump(self.model, 'model_training/xgboost_model.pkl')
        
        logger.info("妯″瀷淇濆瓨瀹屾垚")
    
    def run_training_pipeline(self):
        """杩愯瀹屾暣鐨勮缁冩祦绋?""
        logger.info("=" * 60)
        logger.info("寮€濮媂GBoost妯″瀷璁粌娴佺▼")
        logger.info("=" * 60)
        
        try:
            # 1. 杩炴帴鏁版嵁搴?            self.connect_database()
            
            # 2. 鏁版嵁棰勫鐞?            self.preprocess_data()
            
            # 3. 鍒涘缓鏃堕棿绐楀彛
            self.create_time_windows()
            
            # 4. 鎻愬彇鏃堕棿鐗瑰緛
            self.extract_time_features()
            
            # 5. 鍒涘缓婊戝姩绐楀彛鐗瑰緛
            self.create_sliding_window_features()
            
            # 6. 鏋勯€犳爣绛?            self.create_labels()
            
            # 7. 鏁版嵁娓呮礂
            self.clean_data()
            
            # 8. 鍏抽敭璇嶇紪鐮?            self.encode_keywords()
            
            # 9. 鏁版嵁鍒掑垎
            X_train, X_val, X_test, y_train, y_val, y_test = self.split_data()
            
            # 10. 妯″瀷璁粌
            self.train_model(X_train, y_train, X_val, y_val)
            
            # 11. 妯″瀷璇勪及
            self.evaluate_model(X_test, y_test)
            
            # 12. 淇濆瓨妯″瀷
            self.save_model()
            
            logger.info("=" * 60)
            logger.info("璁粌娴佺▼瀹屾垚")
            logger.info("=" * 60)
            
            return True
            
        except Exception as e:
            logger.error(f"璁粌杩囩▼涓彂鐢熼敊璇? {str(e)}")
            return False

if __name__ == "__main__":
    trainer = XGBoostHotnessTrainer()
    trainer.run_training_pipeline()
