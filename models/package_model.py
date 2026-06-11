#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打包模型文件以便传输到云端服务器
"""

import os
import zipfile
import shutil

def package_model():
    """打包模型文件"""
    
    # 模型路径
    model_dir = "e:/bishe/model_training/pretrained_models/chinese-roberta-wwm-ext"
    output_dir = "e:/bishe/model_training/packages"
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 打包文件名
    zip_filename = os.path.join(output_dir, "chinese-roberta-wwm-ext.zip")
    
    print(f"开始打包模型到: {zip_filename}")
    
    try:
        # 创建ZIP文件
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 遍历模型目录
            for root, dirs, files in os.walk(model_dir):
                for file in files:
                    # 排除不需要的文件
                    if file.startswith('.'):
                        continue
                    
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, model_dir)
                    zipf.write(file_path, arcname)
                    print(f"添加文件: {arcname}")
        
        print(f"模型打包完成: {zip_filename}")
        print(f"文件大小: {os.path.getsize(zip_filename) / (1024 * 1024):.2f} MB")
        
    except Exception as e:
        print(f"打包失败: {e}")

if __name__ == "__main__":
    package_model()
