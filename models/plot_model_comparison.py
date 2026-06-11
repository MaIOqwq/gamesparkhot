#!/usr/bin/env python3
"""
模型性能对比可视化脚本
绘制XGBoost、随机森林和逻辑回归的性能对比柱状图
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']  # 用来正常显示中文标签
plt.rcParams['axes.unicode_minus'] = False  # 用来正常显示负号

def load_data():
    """加载模型对比数据"""
    if not os.path.exists('model_comparison.csv'):
        print("错误：model_comparison.csv文件不存在，请先运行compare_models.py")
        return None
    
    df = pd.read_csv('model_comparison.csv')
    # 将字符串转换为浮点数
    metrics = ['accuracy', 'precision', 'recall', 'f1', 'down_recall', 'up_recall', 'composite_score']
    for metric in metrics:
        df[metric] = df[metric].astype(float)
    
    return df

def plot_performance_comparison(df):
    """绘制性能对比柱状图"""
    models = df['model_name'].tolist()
    metrics = ['accuracy', 'precision', 'recall', 'f1', 'down_recall', 'up_recall']
    metric_names = ['准确率', '精确率', '召回率', 'F1分数', '下降类召回率', '上升类召回率']
    
    # 设置图形大小
    plt.figure(figsize=(16, 6))
    
    # 设置柱状图宽度
    bar_width = 0.25
    
    # 设置位置
    positions = np.arange(len(metrics))
    
    # 颜色设置
    colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0']  # 红色、蓝色、黄色、青色
    
    # 绘制柱状图
    for i, model in enumerate(models):
        model_data = df[df['model_name'] == model]
        values = [model_data[metric].values[0] * 100 for metric in metrics]
        plt.bar(positions + i * bar_width, values, bar_width, label=model, color=colors[i])
    
    # 设置标题和标签
    plt.title('模型性能对比', fontsize=16, fontweight='bold')
    plt.xlabel('评估指标', fontsize=12)
    plt.ylabel('数值（%）', fontsize=12)
    
    # 设置X轴刻度
    plt.xticks(positions + bar_width, metric_names, fontsize=11)
    
    # 设置Y轴范围
    plt.ylim(0, 100)
    
    # 添加图例
    plt.legend(fontsize=10)
    
    # 添加网格线
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    # 添加数值标签
    for i, model in enumerate(models):
        model_data = df[df['model_name'] == model]
        values = [model_data[metric].values[0] * 100 for metric in metrics]
        for j, value in enumerate(values):
            plt.text(positions[j] + i * bar_width, value + 1, f'{value:.1f}',
                     ha='center', va='bottom', fontsize=9)
    
    # 突出XGBoost的F1分数
    xgb_f1 = df[df['model_name'] == 'XGBoost']['f1'].values[0] * 100
    xgb_index = models.index('XGBoost')
    plt.annotate('最高', xy=(3 + xgb_index * bar_width, xgb_f1),
                 xytext=(3 + xgb_index * bar_width, xgb_f1 + 5),
                 arrowprops=dict(facecolor='green', shrink=0.05),
                 fontsize=10, color='green', fontweight='bold')
    
    # 保存图表
    plt.tight_layout()
    plt.savefig('model_performance_comparison.png', dpi=300, bbox_inches='tight')
    print("图表已保存为 model_performance_comparison.png")
    
    # 不显示图表，只保存文件
    # plt.show()

def plot_composite_score(df):
    """绘制综合评分对比图"""
    models = df['model_name'].tolist()
    composite_scores = df['composite_score'].tolist()
    
    # 设置图形大小
    plt.figure(figsize=(10, 5))
    
    # 颜色设置
    colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0']
    
    # 绘制柱状图
    bars = plt.bar(models, [score * 100 for score in composite_scores], color=colors)
    
    # 设置标题和标签
    plt.title('模型综合评分对比', fontsize=16, fontweight='bold')
    plt.xlabel('模型', fontsize=12)
    plt.ylabel('综合评分（%）', fontsize=12)
    
    # 设置Y轴范围
    plt.ylim(50, 70)
    
    # 添加网格线
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    # 添加数值标签
    for bar, score in zip(bars, composite_scores):
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                 f'{score*100:.1f}', ha='center', va='bottom', fontsize=10)
    
    # 突出XGBoost的综合评分
    xgb_score = df[df['model_name'] == 'XGBoost']['composite_score'].values[0] * 100
    xgb_index = models.index('XGBoost')
    plt.annotate('最高', xy=(xgb_index, xgb_score),
                 xytext=(xgb_index, xgb_score + 1),
                 arrowprops=dict(facecolor='green', shrink=0.05),
                 fontsize=10, color='green', fontweight='bold')
    
    # 保存图表
    plt.tight_layout()
    plt.savefig('model_composite_score.png', dpi=300, bbox_inches='tight')
    print("综合评分图表已保存为 model_composite_score.png")
    
    # 不显示图表，只保存文件
    # plt.show()

def plot_recall_comparison(df):
    """绘制上升类和下降类召回率对比图"""
    models = df['model_name'].tolist()
    down_recalls = df['down_recall'].tolist()
    up_recalls = df['up_recall'].tolist()
    
    # 设置图形大小
    plt.figure(figsize=(12, 6))
    
    # 设置柱状图宽度
    bar_width = 0.35
    
    # 设置位置
    positions = np.arange(len(models))
    
    # 颜色设置
    colors = ['#36A2EB', '#FF6384']  # 蓝色（下降类）、红色（上升类）
    
    # 绘制柱状图
    plt.bar(positions - bar_width/2, [score * 100 for score in down_recalls], bar_width, label='下降类召回率', color=colors[0])
    plt.bar(positions + bar_width/2, [score * 100 for score in up_recalls], bar_width, label='上升类召回率', color=colors[1])
    
    # 设置标题和标签
    plt.title('模型召回率对比', fontsize=16, fontweight='bold')
    plt.xlabel('模型', fontsize=12)
    plt.ylabel('召回率（%）', fontsize=12)
    
    # 设置X轴刻度
    plt.xticks(positions, models, fontsize=11)
    
    # 设置Y轴范围
    plt.ylim(0, 100)
    
    # 添加图例
    plt.legend(fontsize=10)
    
    # 添加网格线
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    # 添加数值标签
    for i, (down, up) in enumerate(zip(down_recalls, up_recalls)):
        plt.text(positions[i] - bar_width/2, down * 100 + 1, f'{down*100:.1f}',
                 ha='center', va='bottom', fontsize=9)
        plt.text(positions[i] + bar_width/2, up * 100 + 1, f'{up*100:.1f}',
                 ha='center', va='bottom', fontsize=9)
    
    # 保存图表
    plt.tight_layout()
    plt.savefig('model_recall_comparison.png', dpi=300, bbox_inches='tight')
    print("召回率对比图表已保存为 model_recall_comparison.png")
    
    # 不显示图表，只保存文件
    # plt.show()

def main():
    """主函数"""
    print("加载模型对比数据...")
    df = load_data()
    
    if df is not None:
        print("绘制性能对比柱状图...")
        plot_performance_comparison(df)
        
        print("绘制综合评分对比图...")
        plot_composite_score(df)
        
        print("图表绘制完成！")

if __name__ == '__main__':
    main()