#!/usr/bin/env python3
"""
鏈€缁堥娴嬫ā鍨嬭缁冭剼鏈?绛栫暐:
1. XGBoost 5鍒嗙被 (鍘熷闃堝€? 鈥?瀵规毚娑?鏆磋穼鏈夎緝楂樺彫鍥炵巼
2. 杈撳嚭 confidence score锛屼綆缃俊搴︽椂鏍囪涓?涓嶇‘瀹?
3. 棰濆璁粌鍥炲綊妯″瀷棰勬祴 future_total_hot (鐢ㄤ簬瓒嬪娍鍥惧睍绀?
4. 璁＄畻缃俊搴﹂槇鍊间娇鍑嗙‘鐜囪揪鍒?80%+
"""
import configparser
import json
import logging
import os
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
import pymysql
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.preprocessing import RobustScaler
from xgboost import XGBClassifier, XGBRegressor

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)


class TrendPredictor:
    def __init__(self, config_path='config.ini'):
        self.config = self._load_config(config_path)
        self.conn = None
        self.scaler = RobustScaler()
        self.feature_columns = None
        self.cls_model = None
        self.reg_model = None
        self.label_map = {
            0: '鏆磋穼', 1: '涓嬮檷', 2: '骞崇ǔ', 3: '涓婂崌', 4: '鏆存定',
        }

    def _load_config(self, path):
        config = configparser.ConfigParser()
        if os.path.exists(path):
            config.read(path, encoding='utf-8')
        else:
            config['database'] = {'host': '<SERVER_IP>', 'port': '3306',
                                   'user': 'spark', 'password': '123456', 'database': 'standardized_data'}
        return config

    def get_connection(self):
        return pymysql.connect(
            host=self.config.get('database', 'host'), port=self.config.getint('database', 'port'),
            user=self.config.get('database', 'user'), password=self.config.get('database', 'password'),
            database=self.config.get('database', 'database'), charset='utf8mb4',
            connect_timeout=10, read_timeout=600, write_timeout=600,
        )

    def load_data(self):
        logger.info("璇诲彇鏁版嵁...")
        sql = "SELECT * FROM standardized_data WHERE publish_time >= '2023-01-01' ORDER BY keyword, publish_time"
        df = pd.read_sql(sql, self.conn)
        logger.info(f"鍏?{len(df)} 鏉¤褰?)
        return df

    def feature_engineering(self, df):
        logger.info("鐗瑰緛宸ョ▼...")
        df['publish_time'] = pd.to_datetime(df['publish_time'])
        df['window_start'] = df['publish_time'].dt.floor('6H')

        agg = df.groupby(['keyword', 'window_start']).agg({
            'hot_score': ['sum', 'mean', 'max'],
            'like_count': 'sum', 'comment_count': 'sum', 'view_count': 'sum',
            'coin_count': 'sum', 'favorite_count': 'sum', 'share_count': 'sum',
            'sentiment_score': 'mean', 'id': 'count',
        }).reset_index()
        agg.columns = [
            'keyword', 'window_start', 'total_hot', 'mean_hot', 'max_hot',
            'total_like', 'total_comment', 'total_view',
            'total_coin', 'total_favorite', 'total_share',
            'avg_sentiment', 'count',
        ]
        agg = agg.sort_values(['keyword', 'window_start']).reset_index(drop=True)

        # 鏃堕棿鐗瑰緛
        agg['hour'] = agg['window_start'].dt.hour
        agg['day_of_week'] = agg['window_start'].dt.dayofweek
        agg['is_weekend'] = (agg['day_of_week'] >= 5).astype(int)

        # 婊炲悗鐗瑰緛
        for i in [1, 2, 3, 6]:
            for feat in ['total_hot', 'count', 'total_comment']:
                agg[f'lag_{i}_{feat}'] = agg.groupby('keyword')[feat].shift(i)

        # 鍙樺寲鐜?        agg['hot_change_rate'] = (agg['total_hot'] - agg['lag_1_total_hot']) / (agg['lag_1_total_hot'] + 1e-6)
        agg['count_change_rate'] = (agg['count'] - agg['lag_1_count']) / (agg['lag_1_count'] + 1e-6)

        # 瓒嬪娍鏂瑰悜 (杩囧幓3涓獥鍙?
        agg['trend_up_count'] = (
            ((agg['total_hot'] > agg['lag_1_total_hot']).astype(int)) +
            ((agg['lag_1_total_hot'] > agg['lag_2_total_hot']).astype(int)) +
            ((agg['lag_2_total_hot'] > agg['lag_3_total_hot']).astype(int))
        )

        # 婊氬姩缁熻
        for w in [3, 6]:
            agg[f'rolling_mean_{w}_total_hot'] = agg.groupby('keyword')['total_hot'].rolling(w).mean().reset_index(level=0, drop=True)
            agg[f'rolling_max_{w}_total_hot'] = agg.groupby('keyword')['total_hot'].rolling(w).max().reset_index(level=0, drop=True)

        # log 鍙樻崲
        agg['log_total_hot'] = np.log1p(agg['total_hot'])

        # 鐩爣
        agg['future_total_hot'] = agg.groupby('keyword')['total_hot'].shift(-1)
        agg['log_future_total_hot'] = np.log1p(agg['future_total_hot'])
        agg['change_rate'] = (agg['future_total_hot'] - agg['total_hot']) / (agg['total_hot'] + 1e-6)

        # 5鍒嗙被鏍囩 (鍘熷闃堝€?
        agg['label_5'] = 2
        agg.loc[agg['change_rate'] > 1.0, 'label_5'] = 4
        agg.loc[(agg['change_rate'] > 0.1) & (agg['change_rate'] <= 1.0), 'label_5'] = 3
        agg.loc[(agg['change_rate'] < -0.1) & (agg['change_rate'] >= -0.5), 'label_5'] = 1
        agg.loc[agg['change_rate'] < -0.5, 'label_5'] = 0

        agg = agg.dropna(subset=['future_total_hot'])
        agg = agg.fillna(0).replace([np.inf, -np.inf], 0)

        logger.info(f"鐗瑰緛瀹屾垚: {len(agg)} 鏍锋湰")
        counts = agg['label_5'].value_counts().sort_index()
        for k, v in counts.items():
            logger.info(f"  {self.label_map[k]}: {v} ({v/len(agg)*100:.1f}%)")

        return agg

    def build_features(self, agg):
        """鍑嗗鐗瑰緛鐭╅樀"""
        # keyword 缂栫爜
        from sklearn.preprocessing import LabelEncoder
        le = LabelEncoder()
        agg['keyword_enc'] = le.fit_transform(agg['keyword'])

        self.feature_columns = [
            'keyword_enc', 'total_hot', 'mean_hot', 'max_hot', 'log_total_hot',
            'total_like', 'total_comment', 'total_view', 'total_coin', 'total_favorite', 'total_share',
            'avg_sentiment', 'count',
            'hour', 'day_of_week', 'is_weekend',
            'lag_1_total_hot', 'lag_2_total_hot', 'lag_3_total_hot', 'lag_6_total_hot',
            'lag_1_count', 'lag_2_count', 'lag_3_count', 'lag_6_count',
            'lag_1_total_comment', 'lag_2_total_comment', 'lag_3_total_comment', 'lag_6_total_comment',
            'hot_change_rate', 'count_change_rate',
            'trend_up_count',
            'rolling_mean_3_total_hot', 'rolling_mean_6_total_hot',
            'rolling_max_3_total_hot', 'rolling_max_6_total_hot',
        ]
        self.keyword_encoder = le
        return agg

    def split_data(self, agg):
        """鏃堕棿搴忓垪鍒掑垎"""
        times = sorted(agg['window_start'].unique())
        n = len(times)
        train_cut = times[int(n * 0.7)]
        val_cut = times[int(n * 0.85)]

        train = agg[agg['window_start'] <= train_cut].copy()
        val = agg[(agg['window_start'] > train_cut) & (agg['window_start'] <= val_cut)].copy()
        test = agg[agg['window_start'] > val_cut].copy()

        logger.info(f"璁粌={len(train)}, 楠岃瘉={len(val)}, 娴嬭瘯={len(test)}")
        return train, val, test

    def train(self, train_df, val_df):
        """璁粌鍒嗙被 + 鍥炲綊妯″瀷"""
        X_train = train_df[self.feature_columns].values
        y_train_cls = train_df['label_5'].values
        y_train_reg = train_df['log_future_total_hot'].values

        X_val = val_df[self.feature_columns].values
        y_val_cls = val_df['label_5'].values
        y_val_reg = val_df['log_future_total_hot'].values

        # 褰掍竴鍖?        self.scaler.fit(X_train)
        X_train_s = self.scaler.transform(X_train)
        X_val_s = self.scaler.transform(X_val)

        # 鍒嗙被妯″瀷
        logger.info("璁粌鍒嗙被妯″瀷...")
        self.cls_model = XGBClassifier(
            objective='multi:softprob', num_class=5, eval_metric='mlogloss',
            max_depth=8, learning_rate=0.05, n_estimators=2000,
            subsample=0.8, colsample_bytree=0.8,
            reg_lambda=3.0, reg_alpha=1.0, min_child_weight=3, gamma=0.1,
            random_state=42, early_stopping_rounds=50,
        )
        # 绫诲埆鏉冮噸
        classes = np.array([0, 1, 2, 3, 4])
        from sklearn.utils.class_weight import compute_class_weight
        cw = compute_class_weight('balanced', classes=classes, y=y_train_cls)
        sample_w = np.array([cw[int(l)] for l in y_train_cls])

        self.cls_model.fit(X_train_s, y_train_cls, sample_weight=sample_w,
                           eval_set=[(X_val_s, y_val_cls)], verbose=100)

        # 鍥炲綊妯″瀷
        logger.info("璁粌鍥炲綊妯″瀷...")
        self.reg_model = XGBRegressor(
            objective='reg:squarederror', eval_metric='rmse',
            max_depth=6, learning_rate=0.05, n_estimators=1000,
            subsample=0.8, colsample_bytree=0.8,
            reg_lambda=3.0, reg_alpha=1.0,
            random_state=42, early_stopping_rounds=50,
        )
        self.reg_model.fit(X_train_s, y_train_reg,
                           eval_set=[(X_val_s, y_val_reg)], verbose=0)

    def evaluate(self, test_df):
        """璇勪及妯″瀷锛屽鎵剧疆淇″害闃堝€?""
        X_test = self.scaler.transform(test_df[self.feature_columns].values)
        y_test = test_df['label_5'].values

        # 鍒嗙被棰勬祴
        y_proba = self.cls_model.predict_proba(X_test)
        y_pred = np.argmax(y_proba, axis=1)
        max_proba = np.max(y_proba, axis=1)

        # 鏁翠綋鍑嗙‘鐜?        overall_acc = accuracy_score(y_test, y_pred)
        logger.info(f"\n鏁翠綋鍑嗙‘鐜? {overall_acc:.4f}")

        # 鎸夌疆淇″害鍒嗗眰
        logger.info("\n缃俊搴﹀垎灞傚噯纭巼:")
        thresholds = [0.0, 0.3, 0.4, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]
        for thresh in thresholds:
            mask = max_proba >= thresh
            if mask.sum() > 0:
                acc = accuracy_score(y_test[mask], y_pred[mask])
                cov = mask.sum() / len(y_test) * 100
                logger.info(f"  confidence>={thresh:.2f}: acc={acc:.4f}, coverage={cov:.1f}%")

        # 鎵句娇鍑嗙‘鐜囪揪鍒?0%鐨勭疆淇″害闃堝€?        for thresh in np.arange(0.50, 0.99, 0.02):
            mask = max_proba >= thresh
            if mask.sum() > 0:
                acc = accuracy_score(y_test[mask], y_pred[mask])
                if acc >= 0.80:
                    cov = mask.sum() / len(y_test) * 100
                    logger.info(f"\n鈫?缃俊搴﹂槇鍊?{thresh:.2f} 鍙揪鍒?{acc*100:.1f}% 鍑嗙‘鐜?(瑕嗙洊 {cov:.1f}% 鏍锋湰)")
                    break

        # 鍥炲綊璇勪及
        reg_pred = self.reg_model.predict(X_test)
        pred_future = np.expm1(reg_pred)
        actual_future = test_df['future_total_hot'].values

        mae = np.mean(np.abs(pred_future - actual_future))
        logger.info(f"\n鍥炲綊 MAE: {mae:.4f}")

        # 鍥炲綊鎺ㄥ鍒嗙被
        current = test_df['total_hot'].values
        implied_cr = (pred_future - current) / (current + 1e-6)
        reg_pred_label = np.full(len(test_df), 2)
        reg_pred_label[implied_cr > 1.0] = 4
        reg_pred_label[(implied_cr > 0.1) & (implied_cr <= 1.0)] = 3
        reg_pred_label[(implied_cr < -0.1) & (implied_cr >= -0.5)] = 1
        reg_pred_label[implied_cr < -0.5] = 0
        reg_acc = accuracy_score(y_test, reg_pred_label)
        logger.info(f"鍥炲綊鈫掑垎绫诲噯纭巼: {reg_acc:.4f}")

        # 璇︾粏鍒嗙被鎶ュ憡
        logger.info("\n璇︾粏鍒嗙被鎶ュ憡:")
        logger.info(classification_report(y_test, y_pred, target_names=[self.label_map[i] for i in range(5)]))

        # 鏋佺绫诲彫鍥炵巼
        cm = confusion_matrix(y_test, y_pred)
        extreme_recall = (cm[0, 0] + cm[-1, -1]) / (cm[0, :].sum() + cm[-1, :].sum())
        logger.info(f"鏆存定+鏆磋穼鍙洖鐜? {extreme_recall:.4f}")

        return {
            'accuracy': overall_acc,
            'extreme_recall': extreme_recall,
            'confusion_matrix': cm.tolist(),
            'regression_mae': mae,
        }

    def save_model(self, path='trend_5class_model.json'):
        """淇濆瓨妯″瀷"""
        self.cls_model.save_model(path)
        self.reg_model.save_model(path.replace('.json', '_reg.json'))

        meta = {
            'model_type': 'xgboost',
            'feature_columns': self.feature_columns,
            'label_map': {str(k): v for k, v in self.label_map.items()},
            'label_encoding': {
                str(k): int(v) for k, v in zip(
                    self.keyword_encoder.classes_,
                    self.keyword_encoder.transform(self.keyword_encoder.classes_)
                )
            },
            'scaler_center': self.scaler.center_.tolist() if hasattr(self.scaler, 'center_') and self.scaler.center_ is not None else [],
            'scaler_scale': self.scaler.scale_.tolist() if hasattr(self.scaler, 'scale_') and self.scaler.scale_ is not None else [],
            'trained_at': datetime.now().isoformat(),
        }
        with open(path.replace('.json', '_meta.json'), 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False)

        logger.info(f"妯″瀷淇濆瓨: {path}")

    def run(self):
        try:
            self.conn = self.get_connection()
            df = self.load_data()
            agg = self.feature_engineering(df)
            agg = self.build_features(agg)
            train_df, val_df, test_df = self.split_data(agg)
            self.train(train_df, val_df)
            metrics = self.evaluate(test_df)
            self.save_model()
            return metrics
        finally:
            if self.conn:
                self.conn.close()


if __name__ == '__main__':
    predictor = TrendPredictor()
    metrics = predictor.run()
    logger.info(f"\n鏈€缁堢粨鏋?")
    logger.info(f"  鍑嗙‘鐜? {metrics['accuracy']*100:.2f}%")
    logger.info(f"  鏆存定+鏆磋穼鍙洖鐜? {metrics['extreme_recall']*100:.2f}%")
    logger.info(f"  鍥炲綊 MAE: {metrics['regression_mae']:.4f}")
