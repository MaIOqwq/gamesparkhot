#!/usr/bin/env python3
"""
XGBoost三分类模型训练脚本 - 预测2小时热度趋势
修改自6小时版本，将预测窗口从6小时缩短为2小时
"""

import os
import sys
import configparser
import pymysql
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, classification_report, confusion_matrix
from sklearn.utils.class_weight import compute_class_weight
from xgboost import XGBClassifier
import pickle
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class TrendPredictor2h:
    def __init__(self, config_path: str = 'config.ini'):
        self.config = self._load_config(config_path)
        self.conn = None
        self.label_encoder = LabelEncoder()
        self.model = None
        self.feature_columns = None

    def _load_config(self, config_path: str) -> configparser.ConfigParser:
        config = configparser.ConfigParser()
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        config.read(config_path, encoding='utf-8')
        return config

    def get_connection(self):
        return pymysql.connect(
            host=self.config.get('database', 'host'),
            port=self.config.getint('database', 'port'),
            user=self.config.get('database', 'user'),
            password=self.config.get('database', 'password'),
            database=self.config.get('database', 'database'),
            charset='utf8mb4',
            connect_timeout=10,
            read_timeout=600,
            write_timeout=600
        )

    def init_connection(self):
        self.conn = self.get_connection()
        logger.info("数据库连接成功")

    def close_connection(self):
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.info("数据库连接已关闭")

    def load_data(self):
        logger.info("开始读取数据...")
        start_time = datetime.now()

        sql = """
        SELECT *
        FROM standardized_data
        WHERE publish_time >= '2020-01-01'
        ORDER BY keyword, publish_time
        """

        df = pd.read_sql(sql, self.conn)
        logger.info(f"数据读取完成: 共 {len(df)} 条记录，耗时 {(datetime.now() - start_time).total_seconds():.2f}秒")
        return df

    def feature_engineering(self, df: pd.DataFrame) -> tuple:
        logger.info("开始特征工程...")
        start_time = datetime.now()

        # 时间窗口构造
        df['publish_time'] = pd.to_datetime(df['publish_time'])
        df['window_start'] = df['publish_time'].dt.floor('2H')

        # 按 keyword + window_start 分组聚合
        aggregated = df.groupby(['keyword', 'window_start']).agg({
            'hot_score': 'sum',
            'like_count': 'mean',
            'comment_count': 'mean',
            'view_count': 'mean',
            'coin_count': 'mean',
            'favorite_count': 'mean',
            'share_count': 'mean',
            'danmaku_count': 'mean',
            'sentiment_score': 'mean',
            'author_fans': 'mean',
            'author_level': 'mean',
            'author_post_count': 'mean',
            'has_image': 'mean',
            'has_video': 'mean',
            'id': 'count'
        }).reset_index()

        aggregated.columns = [
            'keyword', 'window_start', 'total_hot', 'avg_like', 'avg_comment',
            'avg_view', 'avg_coin', 'avg_favorite', 'avg_share', 'avg_danmaku',
            'avg_sentiment', 'avg_author_fans', 'avg_author_level',
            'avg_author_post_count', 'image_ratio', 'video_ratio', 'count'
        ]

        # 时间特征
        aggregated['hour'] = aggregated['window_start'].dt.hour
        aggregated['day_of_week'] = aggregated['window_start'].dt.dayofweek
        aggregated['is_weekend'] = aggregated['day_of_week'].apply(lambda x: 1 if x >= 5 else 0)
        aggregated['month'] = aggregated['window_start'].dt.month

        # 历史滑动窗口特征
        logger.info("计算历史滑动窗口特征...")
        features_to_lag = ['total_hot', 'avg_like', 'avg_comment', 'avg_sentiment', 'count']
        for feature in features_to_lag:
            for i in range(1, 4):
                aggregated[f'lag_{i}_{feature}'] = aggregated.groupby('keyword')[feature].shift(i)

        # 计算热度变化率
        aggregated['total_hot_change_rate'] = (
            (aggregated['total_hot'] - aggregated['lag_1_total_hot']) / 
            (aggregated['lag_1_total_hot'] + 1e-6)
        )

        # 计算滚动均值和标准差
        aggregated['rolling_mean_6_total_hot'] = aggregated.groupby('keyword')['total_hot'].rolling(6).mean().reset_index(level=0, drop=True)
        aggregated['rolling_std_6_total_hot'] = aggregated.groupby('keyword')['total_hot'].rolling(6).std().reset_index(level=0, drop=True)

        # 标签构造：预测2小时后的热度（向后移动1个窗口）
        aggregated['future_total_hot'] = aggregated.groupby('keyword')['total_hot'].shift(-1)

        # 丢弃标签为空的样本
        aggregated = aggregated.dropna(subset=['future_total_hot'])

        # 计算变化率
        aggregated['change_rate'] = (
            (aggregated['future_total_hot'] - aggregated['total_hot']) / 
            (aggregated['total_hot'] + 1e-6)
        )

        # 生成三分类标签
        aggregated['label_2h'] = 1  # 默认平稳
        aggregated.loc[aggregated['change_rate'] > 0.1, 'label_2h'] = 2  # 上升
        aggregated.loc[aggregated['change_rate'] < -0.1, 'label_2h'] = 0  # 下降

        # 统计类别分布
        class_counts = aggregated['label_2h'].value_counts()
        logger.info(f"类别分布: {class_counts.to_dict()}")

        # 缺失值处理：填充0
        aggregated = aggregated.fillna(0)

        # 对 keyword 进行 LabelEncoder
        aggregated['keyword_enc'] = self.label_encoder.fit_transform(aggregated['keyword'])

        # 特征选择
        self.feature_columns = [
            'keyword_enc', 'total_hot', 'count',
            'avg_like', 'avg_comment', 'avg_sentiment',
            'lag_1_total_hot', 'lag_2_total_hot', 'lag_3_total_hot',
            'lag_1_avg_like', 'lag_2_avg_like', 'lag_3_avg_like',
            'lag_1_avg_comment', 'lag_2_avg_comment', 'lag_3_avg_comment',
            'lag_1_avg_sentiment', 'lag_2_avg_sentiment', 'lag_3_avg_sentiment',
            'total_hot_change_rate',
            'rolling_mean_6_total_hot', 'rolling_std_6_total_hot',
            'hour', 'day_of_week', 'is_weekend', 'month'
        ]

        logger.info(f"特征工程完成: 共 {len(aggregated)} 条样本，耗时 {(datetime.now() - start_time).total_seconds():.2f}秒")
        return aggregated

    def split_data(self, df: pd.DataFrame):
        logger.info("开始数据划分...")

        train_df = df[df['window_start'] <= '2024-12-31']
        val_df = df[(df['window_start'] > '2024-12-31') & (df['window_start'] <= '2025-12-31')]
        test_df = df[df['window_start'] > '2025-12-31']

        logger.info(f"数据划分完成: 训练集={len(train_df)}, 验证集={len(val_df)}, 测试集={len(test_df)}")

        X_train = train_df[self.feature_columns]
        y_train = train_df['label_2h']
        X_val = val_df[self.feature_columns]
        y_val = val_df['label_2h']
        X_test = test_df[self.feature_columns]
        y_test = test_df['label_2h']

        return X_train, y_train, X_val, y_val, X_test, y_test

    def train_model(self, X_train, y_train, X_val, y_val):
        logger.info("开始模型训练...")
        start_time = datetime.now()

        # 计算类别权重
        class_weights = compute_class_weight('balanced', classes=np.unique(y_train), y=y_train)
        sample_weights = np.array([class_weights[int(label)] for label in y_train])
        logger.info(f"类别权重: {dict(zip([0, 1, 2], class_weights))}")

        # 使用调优后的最佳参数
        params = {
            'objective': 'multi:softprob',
            'num_class': 3,
            'eval_metric': 'mlogloss',
            'max_depth': 5,
            'learning_rate': 0.03,
            'n_estimators': 500,
            'subsample': 0.85,
            'colsample_bytree': 0.9,
            'reg_lambda': 2.0,
            'reg_alpha': 0.5,
            'random_state': 42
        }

        logger.info(f"使用参数: {params}")

        self.model = XGBClassifier(**params)
        self.model.fit(
            X_train, y_train,
            sample_weight=sample_weights,
            eval_set=[(X_val, y_val)],
            early_stopping_rounds=20,
            verbose=100
        )

        logger.info(f"模型训练完成，耗时 {(datetime.now() - start_time).total_seconds():.2f}秒")

    def evaluate_model(self, X_test, y_test):
        logger.info("开始模型评估...")

        y_pred = self.model.predict(X_test)

        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, average='macro')
        recall = recall_score(y_test, y_pred, average='macro')
        f1 = f1_score(y_test, y_pred, average='macro')

        # 计算混淆矩阵
        cm = confusion_matrix(y_test, y_pred)

        logger.info(f"模型评估结果:")
        logger.info(f"准确率 (Accuracy): {accuracy:.4f}")
        logger.info(f"精确率 (Precision): {precision:.4f}")
        logger.info(f"召回率 (Recall): {recall:.4f}")
        logger.info(f"F1分数 (F1 Score): {f1:.4f}")

        # 打印混淆矩阵
        logger.info("\n混淆矩阵:")
        logger.info(f"[[TN, FP, FP]\n[FN, TP, FP]\n[FN, FN, TP]] =\n{cm}")

        # 打印详细的分类报告
        logger.info("\n分类报告:")
        class_report = classification_report(y_test, y_pred, target_names=['下降', '平稳', '上升'])
        logger.info(class_report)

        # 特别关注上升类和下降类的召回率
        class_report_dict = classification_report(y_test, y_pred, target_names=['下降', '平稳', '上升'], output_dict=True)
        logger.info("\n重点关注类别召回率:")
        logger.info(f"下降类召回率: {class_report_dict['下降']['recall']:.4f}")
        logger.info(f"上升类召回率: {class_report_dict['上升']['recall']:.4f}")

        # 计算综合评分
        composite_score = (
            accuracy * 0.4 +
            f1 * 0.3 +
            class_report_dict['下降']['recall'] * 0.15 +
            class_report_dict['上升']['recall'] * 0.15
        )
        logger.info(f"综合评分: {composite_score:.4f}")

        return {
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'down_recall': class_report_dict['下降']['recall'],
            'up_recall': class_report_dict['上升']['recall'],
            'composite_score': composite_score,
            'confusion_matrix': cm.tolist()
        }

    def save_model(self, output_dir: str = '.'):
        os.makedirs(output_dir, exist_ok=True)

        # 保存模型
        model_path = os.path.join(output_dir, 'trend_classifier_2h.json')
        self.model.save_model(model_path)
        logger.info(f"2小时趋势预测模型保存成功: {model_path}")

        # 保存特征列名
        feature_path = os.path.join(output_dir, 'trend_feature_columns_2h.pkl')
        with open(feature_path, 'wb') as f:
            pickle.dump(self.feature_columns, f)
        logger.info(f"特征列名保存成功: {feature_path}")

        # 保存 LabelEncoder
        encoder_path = os.path.join(output_dir, 'trend_label_encoder_2h.pkl')
        with open(encoder_path, 'wb') as f:
            pickle.dump(self.label_encoder, f)
        logger.info(f"LabelEncoder保存成功: {encoder_path}")

        # 保存类别映射字典
        class_map_path = os.path.join(output_dir, 'trend_class_map_2h.pkl')
        class_map = {0: '下降', 1: '平稳', 2: '上升'}
        with open(class_map_path, 'wb') as f:
            pickle.dump(class_map, f)
        logger.info(f"类别映射字典保存成功: {class_map_path}")

    def run(self, output_dir: str = '.'):
        try:
            self.init_connection()

            df = self.load_data()
            processed_df = self.feature_engineering(df)
            X_train, y_train, X_val, y_val, X_test, y_test = self.split_data(processed_df)

            self.train_model(X_train, y_train, X_val, y_val)
            metrics = self.evaluate_model(X_test, y_test)
            self.save_model(output_dir)

            logger.info("=" * 60)
            logger.info("2小时热度趋势预测模型训练完成")
            logger.info("=" * 60)
            
            return 0

        except pymysql.Error as e:
            logger.error(f"数据库错误: {e}")
            return 1
        except FileNotFoundError as e:
            logger.error(f"配置文件错误: {e}")
            return 1
        except Exception as e:
            logger.error(f"未知错误: {e}")
            import traceback
            traceback.print_exc()
            return 1
        finally:
            self.close_connection()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='XGBoost三分类模型训练脚本 - 预测2小时热度趋势'
    )
    parser.add_argument(
        '--config',
        default='config.ini',
        help='配置文件路径（默认: config.ini）'
    )
    parser.add_argument(
        '--output',
        default='.',
        help='输出目录（默认: 当前目录）'
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("XGBoost 2小时热度趋势预测模型训练脚本启动")
    logger.info("=" * 60)

    predictor = TrendPredictor2h(config_path=args.config)
    exit_code = predictor.run(output_dir=args.output)

    logger.info("=" * 60)
    logger.info(f"脚本结束，退出码: {exit_code}")
    logger.info("=" * 60)

    exit(exit_code)


if __name__ == '__main__':
    main()