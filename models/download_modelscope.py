#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用ModelScope下载模型
"""

import os
import sys

# 设置backports.zoneinfo为zoneinfo
sys.modules['zoneinfo'] = __import__('backports.zoneinfo')

from modelscope.hub.snapshot_download import snapshot_download

def download_model():
    """下载预训练模型"""
    # 模型名称
    model_name = "dienstag/chinese-roberta-wwm-ext"
    
    # 保存目录
    save_dir = "e:/bishe/model_training/pretrained_models/chinese-roberta-wwm-ext"
    
    # 创建保存目录
    os.makedirs(save_dir, exist_ok=True)
    
    print(f"开始下载模型: {model_name}")
    print(f"保存路径: {save_dir}")
    
    try:
        # 使用modelscope下载模型
        local_dir = snapshot_download(
            model_name,
            local_dir=save_dir,
            cache_dir=save_dir
        )
        
        print(f"模型已成功下载到: {local_dir}")
        
    except Exception as e:
        print(f"下载失败: {e}")

if __name__ == "__main__":
    download_model()
