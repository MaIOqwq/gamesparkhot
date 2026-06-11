#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
下载预训练模型到本地
"""

from transformers import AutoTokenizer, AutoModel
import os

def download_model():
    """下载预训练模型"""
    # 模型名称
    model_name = "hfl/chinese-roberta-wwm-ext"
    
    # 保存目录
    save_dir = "e:/bishe/model_training/pretrained_models/chinese-roberta-wwm-ext"
    
    # 创建保存目录
    os.makedirs(save_dir, exist_ok=True)
    
    print(f"开始下载模型: {model_name}")
    print(f"保存路径: {save_dir}")
    
    try:
        # 下载分词器
        print("正在下载分词器...")
        tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=save_dir)
        tokenizer.save_pretrained(save_dir)
        print("分词器下载完成")
        
        # 下载模型
        print("正在下载模型...")
        model = AutoModel.from_pretrained(model_name, cache_dir=save_dir)
        model.save_pretrained(save_dir)
        print("模型下载完成")
        
        print(f"模型已成功下载到: {save_dir}")
        
    except Exception as e:
        print(f"下载失败: {e}")

if __name__ == "__main__":
    download_model()
