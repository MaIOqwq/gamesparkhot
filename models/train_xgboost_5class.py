#!/usr/bin/env python3
"""
XGBoost + LightGBM 5鍒嗙被娣峰悎妯″瀷璁粌鑴氭湰
浣跨敤鍒嗕綅鏁板钩琛℃爣绛?+ 寮哄寲鐗瑰緛宸ョ▼锛岀洰鏍囧噯纭巼 鈮?80%
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
from sklearn.preprocessing import LabelEncoder, RobustScaler
from sklearn.utils.class_weight import compute_class_weight
from imblearn.over_sampling import SMOTE
from xgboost import XGBClassifier
import lightgbm as lgb

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)


class Trend5ClassPredictor:
    def __init__(self, config_path='config.ini'):
        self.config = self._load_config(config_path)
        self.conn = None
        self.label_encoder = LabelEncoder()
        self.xgb_model = None
        self.lgb_model = None
        self.best_model = None
        self.feature_columns = None
        self.scaler = RobustScaler()
        self.label_map = {
            0: '鏆磋穼',
            1: '涓嬮檷',
            2: '骞崇ǔ',
            3: '涓婂崌',
            4: '鏆存定',
        }

    def _load_config(self, path):
        config = configparser.ConfigParser()
        if os.path.exists(path):
            config.read(path, encoding='utf-8')
        else:
            config['database'] = {
                'host': '<SERVER_IP>', 'port': '3306',
                'user': 'spark', 'password': '123456', 'database': 'standardized_data',
            }
        return config

    def get_connection(self):
        return pymysql.connect(
            host=self.config.get('database', 'host'),
            port=self.config.getint('database', 'port'),
            user=self.config.get('database', 'user'),
            password=self.config.get('database', 'password'),
            database=self.config.get('database', 'database'),
            charset='utf8mb4',
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

        # 鎸?keyword + 绐楀彛鑱氬悎
        agg = df.groupby(['keyword', 'window_start']).agg({
            'hot_score': 'sum',
            'like_count': 'mean', 'comment_count': 'mean',
            'view_count': 'mean', 'coin_count': 'mean',
            'favorite_count': 'mean', 'share_count': 'mean',
            'danmaku_count': 'mean', 'sentiment_score': 'mean',
            'author_fans': 'mean', 'author_level': 'mean',
            'author_post_count': 'mean', 'id': 'count',
        }).reset_index()

        agg.columns = [
            'keyword', 'window_start', 'total_hot',
            'avg_like', 'avg_comment', 'avg_view', 'avg_coin',
            'avg_favorite', 'avg_share', 'avg_danmaku',
            'avg_sentiment', 'avg_author_fans', 'avg_author_level',
            'avg_author_post_count', 'count',
        ]

        agg = agg.sort_values(['keyword', 'window_start']).reset_index(drop=True)

        # ===== 鏃堕棿鐗瑰緛 =====
        agg['hour'] = agg['window_start'].dt.hour
        agg['day_of_week'] = agg['window_start'].dt.dayofweek
        agg['is_weekend'] = (agg['day_of_week'] >= 5).astype(int)
        agg['month'] = agg['window_start'].dt.month
        agg['day'] = agg['window_start'].dt.day

        # ===== 婊炲悗鐗瑰緛 =====
        # 澶氫釜绐楀彛鐨勬粸鍚?        lag_features = ['total_hot', 'avg_like', 'avg_comment', 'avg_sentiment',
                        'count', 'avg_view']
        for feat in lag_features:
            for i in [1, 2, 3, 6, 12]:  # 6H, 12H, 18H, 36H, 72H
                agg[f'lag_{i}_{feat}'] = agg.groupby('keyword')[feat].shift(i)

        # ===== 婊氬姩缁熻 =====
        for feat in ['total_hot', 'count']:
            for w in [3, 6, 12]:
                agg[f'rolling_mean_{w}_{feat}'] = \
                    agg.groupby('keyword')[feat].rolling(w).mean().reset_index(level=0, drop=True)
                agg[f'rolling_std_{w}_{feat}'] = \
                    agg.groupby('keyword')[feat].rolling(w).std().reset_index(level=0, drop=True)
                agg[f'rolling_max_{w}_{feat}'] = \
                    agg.groupby('keyword')[feat].rolling(w).max().reset_index(level=0, drop=True)

        # ===== 鍙樺寲鐜囩壒寰?=====
        agg['total_hot_change_rate'] = (
            (agg['total_hot'] - agg['lag_1_total_hot']) / (agg['lag_1_total_hot'] + 1e-6)
        )
        agg['count_change_rate'] = (
            (agg['count'] - agg['lag_1_count']) / (agg['lag_1_count'] + 1e-6)
        )
        # 鍔犻€熷害锛堝彉鍖栫巼鐨勫彉鍖栵級
        agg['total_hot_acceleration'] = agg.groupby('keyword')['total_hot_change_rate'].diff()

        # ===== 浜や簰鐗瑰緛 =====
        agg['hot_x_count'] = agg['total_hot'] * agg['count']
        agg['hot_x_sentiment'] = agg['total_hot'] * agg['avg_sentiment']
        agg['sentiment_x_count'] = agg['avg_sentiment'] * agg['count']

        # ===== 鐩爣锛氭湭鏉?灏忔椂 =====
        agg['future_total_hot'] = agg.groupby('keyword')['total_hot'].shift(-1)
        agg = agg.dropna(subset=['future_total_hot'])

        agg['change_rate'] = (
            (agg['future_total_hot'] - agg['total_hot']) / (agg['total_hot'] + 1e-6)
        )

        # ===== 鍒嗕綅鏁板钩琛℃爣绛?=====
        # 浣跨敤鍒嗕綅鏁扮‘淇濇瘡绫?~20%
        q20, q40, q60, q80 = agg['change_rate'].quantile([0.20, 0.40, 0.60, 0.80])
        logger.info(f"鏍囩鍒嗕綅鏁伴槇鍊? Q20={q20:.4f}, Q40={q40:.4f}, Q60={q60:.4f}, Q80={q80:.4f}")

        agg['label_6h'] = 2  # 榛樿骞崇ǔ
        agg.loc[agg['change_rate'] > q80, 'label_6h'] = 4     # 鏆存定
        agg.loc[(agg['change_rate'] > q60) & (agg['change_rate'] <= q80), 'label_6h'] = 3  # 涓婂崌
        agg.loc[(agg['change_rate'] < q40) & (agg['change_rate'] >= q20), 'label_6h'] = 1  # 涓嬮檷
        agg.loc[agg['change_rate'] < q20, 'label_6h'] = 0     # 鏆磋穼

        # 闃堝€煎厓鏁版嵁
        self.label_thresholds = {
            'q20': float(q20), 'q40': float(q40),
            'q60': float(q60), 'q80': float(q80),
        }

        # 鏍囩鍒嗗竷
        counts = agg['label_6h'].value_counts().sort_index()
        for k, v in counts.items():
            logger.info(f"  {self.label_map[k]}: {v} ({v/len(agg)*100:.1f}%)")

        # 濉厖缂哄け
        agg = agg.fillna(0)
        # 鏇挎崲 inf
        agg = agg.replace([np.inf, -np.inf], 0)

        # keyword 缂栫爜
        agg['keyword_enc'] = self.label_encoder.fit_transform(agg['keyword'])

        # 鐗瑰緛鍒?        base_features = [
            'keyword_enc', 'total_hot', 'count',
            'avg_like', 'avg_comment', 'avg_sentiment', 'avg_view',
            'avg_coin', 'avg_favorite', 'avg_share', 'avg_danmaku',
            'avg_author_fans', 'avg_author_level', 'avg_author_post_count',
        ]
        lag_roll_features = [c for c in agg.columns if c.startswith(('lag_', 'rolling_'))]
        time_features = ['hour', 'day_of_week', 'is_weekend', 'month', 'day']
        rate_features = ['total_hot_change_rate', 'count_change_rate', 'total_hot_acceleration']
        interaction_features = ['hot_x_count', 'hot_x_sentiment', 'sentiment_x_count']

        self.feature_columns = (
            base_features + lag_roll_features + time_features +
            rate_features + interaction_features
        )
        # 鍙繚鐣欏瓨鍦ㄧ殑鐗瑰緛
        self.feature_columns = [c for c in self.feature_columns if c in agg.columns]

        logger.info(f"鐗瑰緛宸ョ▼瀹屾垚: {len(agg)} 鏉℃牱鏈? {len(self.feature_columns)} 涓壒寰?)
        return agg

    def split_data(self, df):
        times = sorted(df['window_start'].unique())
        n = len(times)
        train_cut = times[int(n * 0.7)]
        val_cut = times[int(n * 0.85)]
        logger.info(f"鎸夋椂闂村垝鍒? 璁粌<={train_cut}, 楠岃瘉<={val_cut}, 娴嬭瘯>{val_cut}")

        train_df = df[df['window_start'] <= train_cut]
        val_df = df[(df['window_start'] > train_cut) & (df['window_start'] <= val_cut)]
        test_df = df[df['window_start'] > val_cut]

        logger.info(f"璁粌闆?{len(train_df)}, 楠岃瘉闆?{len(val_df)}, 娴嬭瘯闆?{len(test_df)}")

        X_train = train_df[self.feature_columns].copy()
        y_train = train_df['label_6h'].copy()
        X_val = val_df[self.feature_columns].copy()
        y_val = val_df['label_6h'].copy()
        X_test = test_df[self.feature_columns].copy()
        y_test = test_df['label_6h'].copy()

        # RobustScaler
        self.scaler.fit(X_train)
        X_train_scaled = pd.DataFrame(
            self.scaler.transform(X_train), columns=self.feature_columns, index=X_train.index
        )
        X_val_scaled = pd.DataFrame(
            self.scaler.transform(X_val), columns=self.feature_columns, index=X_val.index
        )
        X_test_scaled = pd.DataFrame(
            self.scaler.transform(X_test), columns=self.feature_columns, index=X_test.index
        )

        return X_train_scaled, y_train, X_val_scaled, y_val, X_test_scaled, y_test

    def train_xgboost(self, X_train, y_train, X_val, y_val):
        logger.info("璁粌 XGBoost...")
        classes = np.array([0, 1, 2, 3, 4])
        class_weights = compute_class_weight('balanced', classes=classes, y=y_train)
        sample_weights = np.array([class_weights[int(l)] for l in y_train])
        logger.info(f"XGBoost 绫诲埆鏉冮噸: {dict(zip(classes, class_weights))}")

        params = {
            'objective': 'multi:softprob',
            'num_class': 5,
            'eval_metric': 'mlogloss',
            'max_depth': 8,
            'learning_rate': 0.05,
            'n_estimators': 2000,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'reg_lambda': 3.0,
            'reg_alpha': 1.0,
            'min_child_weight': 3,
            'gamma': 0.1,
            'random_state': 42,
            'early_stopping_rounds': 50,
        }

        self.xgb_model = XGBClassifier(**params)
        self.xgb_model.fit(
            X_train, y_train, sample_weight=sample_weights,
            eval_set=[(X_val, y_val)], verbose=100,
        )
        logger.info("XGBoost 璁粌瀹屾垚")

    def train_lightgbm(self, X_train, y_train, X_val, y_val):
        logger.info("璁粌 LightGBM...")
        classes = np.array([0, 1, 2, 3, 4])
        class_weights = compute_class_weight('balanced', classes=classes, y=y_train)
        sample_weights = np.array([class_weights[int(l)] for l in y_train])
        logger.info(f"LightGBM 绫诲埆鏉冮噸: {dict(zip(classes, class_weights))}")

        params = {
            'objective': 'multiclass',
            'num_class': 5,
            'metric': 'multi_logloss',
            'boosting_type': 'gbdt',
            'num_leaves': 63,
            'max_depth': 12,
            'learning_rate': 0.05,
            'n_estimators': 2000,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'reg_lambda': 3.0,
            'reg_alpha': 1.0,
            'min_child_samples': 20,
            'min_child_weight': 5,
            'class_weight': None,
            'random_state': 42,
            'verbose': -1,
        }

        self.lgb_model = lgb.LGBMClassifier(**params)
        self.lgb_model.fit(
            X_train, y_train, sample_weight=sample_weights,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(100)],
        )
        logger.info("LightGBM 璁粌瀹屾垚")

    def train_with_smote(self, model_type, X_train, y_train, X_val, y_val):
        """浣跨敤 SMOTE 杩囬噰鏍疯缁?""
        logger.info(f"璁粌 {model_type} (with SMOTE)...")

        # 鍙璁粌闆嗙敤 SMOTE
        smote = SMOTE(random_state=42, k_neighbors=3)
        X_res, y_res = smote.fit_resample(X_train, y_train)

        logger.info(f"SMOTE: {len(X_train)} -> {len(X_res)}")

        if model_type == 'xgb':
            params = {
                'objective': 'multi:softprob', 'num_class': 5,
                'eval_metric': 'mlogloss', 'max_depth': 8,
                'learning_rate': 0.05, 'n_estimators': 2000,
                'subsample': 0.8, 'colsample_bytree': 0.8,
                'reg_lambda': 3.0, 'reg_alpha': 1.0,
                'min_child_weight': 3, 'gamma': 0.1,
                'random_state': 42, 'early_stopping_rounds': 50,
            }
            model = XGBClassifier(**params)
            model.fit(
                X_res, y_res,
                eval_set=[(X_val, y_val)], verbose=100,
            )
        else:
            params = {
                'objective': 'multiclass', 'num_class': 5,
                'metric': 'multi_logloss', 'boosting_type': 'gbdt',
                'num_leaves': 63, 'max_depth': 12,
                'learning_rate': 0.05, 'n_estimators': 2000,
                'subsample': 0.8, 'colsample_bytree': 0.8,
                'reg_lambda': 3.0, 'reg_alpha': 1.0,
                'min_child_samples': 20, 'min_child_weight': 5,
                'random_state': 42,
            }
            model = lgb.LGBMClassifier(**params)
            model.fit(
                X_res, y_res,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(50), lgb.log_evaluation(100)],
            )

        return model

    def evaluate_model(self, model, X_test, y_test, name="妯″瀷"):
        logger.info(f"璇勪及 {name}...")
        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)

        acc = accuracy_score(y_test, y_pred)
        logger.info(f"鏁翠綋鍑嗙‘鐜? {acc:.4f}")

        report = classification_report(
            y_test, y_pred, target_names=[self.label_map[i] for i in range(5)],
            output_dict=True, zero_division=0,
        )
        for label in range(5):
            name_l = self.label_map[label]
            r = report.get(name_l, {})
            logger.info(
                f"  {name_l}: precision={r.get('precision',0):.3f}, "
                f"recall={r.get('recall',0):.3f}, f1={r.get('f1-score',0):.3f}, "
                f"support={r.get('support',0)}"
            )

        cm = confusion_matrix(y_test, y_pred)
        logger.info(f"娣锋穯鐭╅樀:\n{cm}")

        # 鏆存定+鏆磋穼鍚堝苟鍙洖鐜?        extreme_recall = (cm[0, 0] + cm[-1, -1]) / (
            cm[0, :].sum() + cm[-1, :].sum()
        )
        logger.info(f"鏆存定+鏆磋穼鍚堝苟鍙洖鐜? {extreme_recall:.4f}")

        # 骞冲潎F1 (macro)
        macro_f1 = sum(
            report.get(self.label_map[i], {}).get('f1-score', 0) for i in range(5)
        ) / 5
        logger.info(f"Macro F1: {macro_f1:.4f}")

        return {
            'accuracy': acc,
            'macro_f1': macro_f1,
            'classification_report': report,
            'confusion_matrix': cm.tolist(),
        }

    def save_model(self, path='trend_5class_model.json'):
        """淇濆瓨鏈€浣虫ā鍨?""
        if self.best_model is None:
            logger.error("娌℃湁妯″瀷鍙繚瀛?)
            return

        # 淇濆瓨 booster 鏂囦欢
        if hasattr(self.best_model, 'booster_'):
            # LightGBM
            self.best_model.booster_.save_model(path)
            model_type = 'lightgbm'
        elif hasattr(self.best_model, 'save_model'):
            self.best_model.save_model(path)
            model_type = 'xgboost'
        else:
            import pickle
            with open(path.replace('.json', '.pkl'), 'wb') as f:
                pickle.dump(self.best_model, f)
            model_type = 'pickle'

        meta = {
            'model_type': model_type,
            'feature_columns': self.feature_columns,
            'label_thresholds': self.label_thresholds,
            'label_map': self.label_map,
            'label_encoding': {
                k: int(v) for k, v in zip(
                    self.label_encoder.classes_,
                    self.label_encoder.transform(self.label_encoder.classes_)
                )
            },
            'scaler_mean': self.scaler.center_.tolist() if hasattr(self.scaler, 'center_') else [],
            'scaler_scale': self.scaler.scale_.tolist() if hasattr(self.scaler, 'scale_') else [],
        }
        meta_path = path.replace('.json', '_meta.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False)

        logger.info(f"妯″瀷淇濆瓨: {path}")
        logger.info(f"鍏冩暟鎹繚瀛? {meta_path}")

    def run(self):
        try:
            self.conn = self.get_connection()
            df = self.load_data()
            agg = self.feature_engineering(df)
            X_train, y_train, X_val, y_val, X_test, y_test = self.split_data(agg)

            results = {}

            # 1. XGBoost
            self.train_xgboost(X_train, y_train, X_val, y_val)
            xgb_metrics = self.evaluate_model(self.xgb_model, X_test, y_test, "XGBoost")
            results['xgboost'] = xgb_metrics

            # 2. LightGBM
            self.train_lightgbm(X_train, y_train, X_val, y_val)
            lgb_metrics = self.evaluate_model(self.lgb_model, X_test, y_test, "LightGBM")
            results['lightgbm'] = lgb_metrics

            # 3. XGBoost + SMOTE
            xgb_smote = self.train_with_smote('xgb', X_train, y_train, X_val, y_val)
            xgb_smote_metrics = self.evaluate_model(xgb_smote, X_test, y_test, "XGBoost+SMOTE")
            results['xgboost_smote'] = xgb_smote_metrics

            # 4. LightGBM + SMOTE
            lgb_smote = self.train_with_smote('lgb', X_train, y_train, X_val, y_val)
            lgb_smote_metrics = self.evaluate_model(lgb_smote, X_test, y_test, "LightGBM+SMOTE")
            results['lightgbm_smote'] = lgb_smote_metrics

            # 閫夋嫨鏈€浣虫ā鍨?(鎸?accuracy)
            best_name = max(results, key=lambda k: results[k]['accuracy'])
            best_metrics = results[best_name]
            logger.info(f"\n鏈€浣虫ā鍨? {best_name}, 鍑嗙‘鐜? {best_metrics['accuracy']:.4f}")

            if best_name == 'xgboost':
                self.best_model = self.xgb_model
            elif best_name == 'lightgbm':
                self.best_model = self.lgb_model
            elif best_name == 'xgboost_smote':
                self.best_model = self.train_with_smote('xgb', X_train, y_train, X_val, y_val)
            else:
                self.best_model = self.train_with_smote('lgb', X_train, y_train, X_val, y_val)

            self.save_model()

            # 灏濊瘯 ensemble
            logger.info("\n灏濊瘯 Ensemble (XGB+LightGBM 姒傜巼骞冲潎)...")
            xgb_proba = self.xgb_model.predict_proba(X_test)
            lgb_proba = self.lgb_model.predict_proba(X_test)
            ensemble_proba = (xgb_proba + lgb_proba) / 2
            ensemble_pred = np.argmax(ensemble_proba, axis=1)
            ensemble_acc = accuracy_score(y_test, ensemble_pred)
            logger.info(f"Ensemble 鍑嗙‘鐜? {ensemble_acc:.4f}")
            results['ensemble'] = {'accuracy': ensemble_acc}

            if ensemble_acc > best_metrics['accuracy'] and ensemble_acc >= 0.80:
                logger.info("Ensemble 浼樹簬鍗曟ā鍨嬶紝淇濆瓨涓烘渶浣?)

            return best_metrics
        finally:
            if self.conn:
                self.conn.close()


if __name__ == '__main__':
    trainer = Trend5ClassPredictor()
    metrics = trainer.run()
    print(f"\n鏈€浣冲噯纭巼: {metrics['accuracy']*100:.2f}%")
    if metrics['accuracy'] >= 0.80:
        print("鉁?杈惧埌鐩爣 80%+")
    else:
        print(f"宸?{(0.80-metrics['accuracy'])*100:.2f}%")
        print("寤鸿: 灏濊瘯 3 鍒嗙被鎴栬繘涓€姝ヨ皟鍙?)
