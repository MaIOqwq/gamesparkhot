#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XGBoost热点分类模型预测脚本（纯Python版）
"""

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

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="XGBoost热点分类模型预测脚本")
    parser.add_argument("--model_path", default="./hotspot_classifier.json",
                      help="XGBoost模型路径")
    parser.add_argument("--feature_columns_path", default="./feature_columns.pkl",
                      help="特征列名文件路径")
    parser.add_argument("--label_encoder_path", default="./label_encoder.pkl",
                      help="LabelEncoder文件路径")
    parser.add_argument("--output_dir", default="./predictions",
                      help="输出目录，用于保存JSON结果")
    
    args = parser.parse_args()
    
    logger.info("=======================================")
    logger.info("XGBoost热点分类模型预测开始")
    logger.info("=======================================")
    
    try:
        # 加载模型
        logger.info("开始加载模型...")
        model = xgb.Booster()
        model.load_model(args.model_path)
        logger.info(f"模型加载成功: {args.model_path}")
        
        # 加载特征列名
        with open(args.feature_columns_path, 'rb') as f:
            feature_columns = pickle.load(f)
        logger.info(f"特征列名加载成功: {args.feature_columns_path}")
        logger.info(f"特征列数: {len(feature_columns)}")
        logger.info(f"特征列: {feature_columns[:5]}...")
        
        # 加载LabelEncoder
        with open(args.label_encoder_path, 'rb') as f:
            label_encoder = pickle.load(f)
        logger.info(f"LabelEncoder加载成功: {args.label_encoder_path}")
        
        # 生成模拟特征数据
        logger.info("开始模拟预测...")
        
        # 生成随机特征数据
        num_samples = 5
        feature_matrix = np.random.rand(num_samples, len(feature_columns))
        
        # 转换为DMatrix，指定特征名称
        dmatrix = xgb.DMatrix(feature_matrix, feature_names=feature_columns)
        
        # 预测概率
        probabilities = model.predict(dmatrix)
        
        # 生成预测结果
        window_start = datetime.now()
        predict_time = datetime.now()
        predictions = []
        keywords = ['游戏', '手机', '科技', '电影', '音乐']
        
        for i, prob in enumerate(probabilities):
            keyword = keywords[i % len(keywords)]
            is_hot = 1 if prob >= 0.45 else 0
            predictions.append({
                "keyword": keyword,
                "window_start": window_start.strftime("%Y-%m-%d %H:%M:%S"),
                "predict_time": predict_time.strftime("%Y-%m-%d %H:%M:%S"),
                "probability": float(prob),
                "is_hot": is_hot,
                "model_version": "v1.0"
            })
        
        # 输出JSON结果到本地文件
        if args.output_dir and predictions:
            os.makedirs(args.output_dir, exist_ok=True)
            output_file = os.path.join(args.output_dir, f"hotspot_predictions_{window_start.strftime('%Y%m%d_%H%M%S')}.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(predictions, f, ensure_ascii=False, indent=2)
            logger.info(f"预测结果已保存到: {output_file}")
        
        logger.info(f"预测完成: 共 {len(predictions)} 条预测结果")
        for pred in predictions:
            logger.info(f"关键词: {pred['keyword']}, 概率: {pred['probability']:.4f}, 是否热点: {pred['is_hot']}")
        
        logger.info("=======================================")
        logger.info("XGBoost热点分类模型预测结束")
        logger.info("=======================================")
        
        return 0
    except Exception as e:
        logger.error(f"预测流程失败: {e}")
        import traceback
        traceback.print_exc()
        logger.info("=======================================")
        logger.info("XGBoost热点分类模型预测失败")
        logger.info("=======================================")
        return 1

if __name__ == "__main__":
    sys.exit(main())