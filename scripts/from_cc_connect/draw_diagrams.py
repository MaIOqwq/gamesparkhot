import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Ellipse, Polygon
from matplotlib.font_manager import FontProperties
import numpy as np
import os

fig_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'figures')
fp = FontProperties(fname=os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Fonts', 'simhei.ttf'), size=9)
fp_b = FontProperties(fname=os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Fonts', 'simhei.ttf'), size=11, weight='bold')
fp_s = FontProperties(fname=os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Fonts', 'simhei.ttf'), size=7)
fp_t = FontProperties(fname=os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Fonts', 'simhei.ttf'), size=13, weight='bold')
bc = '#2C3E50'

# ============================================================
# ER DIAGRAM (Chen Notation) - fixed connections
# ============================================================
def draw_er():
    fig, ax = plt.subplots(1, 1, figsize=(9.5, 7.5))
    ax.set_xlim(0, 9.5)
    ax.set_ylim(0, 7.5)
    ax.axis('off')

    def rect(x, y, w, h, text, sub=''):
        r = FancyBboxPatch((x-w/2, y-h/2), w, h, boxstyle="round,pad=0.05",
                           facecolor='#D6EAF8', edgecolor=bc, linewidth=2.5, zorder=3)
        ax.add_patch(r)
        ax.text(x, y+0.05, text, ha='center', va='center', fontproperties=fp_b)
        if sub:
            ax.text(x, y-0.18, sub, ha='center', va='center', fontproperties=fp_s, color='#555')

    def attr(x, y, text):
        e = Ellipse((x, y), width=1.4, height=0.38, facecolor='#FEF9E7', edgecolor=bc, linewidth=2, zorder=3)
        ax.add_patch(e)
        ax.text(x, y, text, ha='center', va='center', fontproperties=fp)

    def diam(x, y, text):
        pts = [(x, y+0.22), (x+0.7, y), (x, y-0.22), (x-0.7, y)]
        d = Polygon(pts, closed=True, facecolor='#D5F5E3', edgecolor=bc, linewidth=2.5, zorder=3)
        ax.add_patch(d)
        ax.text(x, y, text, ha='center', va='center', fontproperties=fp)

    def ln(x1, y1, x2, y2):
        ax.plot([x1, x2], [y1, y2], color=bc, linewidth=2, solid_capstyle='round', zorder=2)

    # === ENTITIES ===
    rect(4.7, 6.2, 2.2, 0.7, '爬虫任务队列', '(crawl_queue)')
    rect(4.7, 4.3, 2.5, 0.7, '爬虫输出原始数据', '(Kafka 消息)')
    rect(4.7, 2.4, 2.5, 0.7, '标准化舆情数据', '(standardized_data)')
    rect(4.7, 0.6, 2.0, 0.6, '内容指标', '(content_metrics)')

    # === Queue ATTRIBUTES ===
    for x, y, t in [(0.5, 7.0, 'task_id (PK)'), (2.2, 7.0, 'keyword'), (4.7, 7.45, 'platform'),
                    (7.2, 7.0, 'status'), (8.9, 7.0, 'last_crawl_time')]:
        attr(x, y, t)
        ax.plot([x, x], [y-0.19, 6.55], color=bc, linewidth=2, zorder=2)

    # === RawData ATTRIBUTES ===
    for x, y, t in [(0.5, 5.1, 'raw_id (PK)'), (2.2, 5.1, 'content'), (4.7, 5.55, 'keyword'),
                    (7.2, 5.1, 'publish_time'), (8.9, 5.1, 'platform')]:
        attr(x, y, t)
        ax.plot([x, x], [y-0.19, 4.65], color=bc, linewidth=2, zorder=2)

    # === StdData ATTRIBUTES ===
    for x, y, t in [(0.3, 3.2, 'id (PK)'), (2.0, 3.2, 'raw_id (UK)'), (4.0, 3.65, 'keyword'),
                    (6.5, 3.2, 'hot_score'), (8.5, 2.9, 'sentiment_score'), (8.5, 3.5, 'publish_time')]:
        attr(x, y, t)
        ax.plot([x, x], [y-0.19, 2.75], color=bc, linewidth=2, zorder=2)

    # === Metrics ATTRIBUTES ===
    for x, y, t in [(1.1, -0.1, 'id (PK)'), (2.8, -0.4, 'data_id (FK)'),
                    (4.7, 0.0, 'hot_raw'), (6.6, -0.4, 'hot_score'), (8.3, -0.1, 'text_length')]:
        attr(x, y, t)
        ax.plot([x, x], [y+0.19, 0.9], color=bc, linewidth=2, zorder=2)

    # === RELATIONSHIPS ===
    diam(4.7, 5.35, '产生')
    diam(4.7, 3.45, '清洗转换')
    diam(4.7, 1.55, '指标计算')

    # Connect lines
    for y1, y2 in [(5.85, 5.57), (5.13, 4.65), (3.95, 3.67), (3.23, 2.75), (2.05, 1.77), (1.33, 0.9)]:
        ax.plot([4.7, 4.7], [y1, y2], color=bc, linewidth=2, zorder=2)

    # Cardinality
    for x, y, t in [(5.15, 5.65, '1'), (5.15, 5.1, 'N'), (5.15, 3.8, '1'),
                    (5.15, 3.2, '1'), (5.15, 1.9, '1'), (5.15, 1.3, '1')]:
        ax.text(x, y, t, fontsize=10, fontweight='bold')

    ax.text(0.3, -0.45, 'PK = Primary Key    UK = Unique Key    FK = Foreign Key', fontproperties=fp_s)
    plt.savefig(os.path.join(fig_dir, 'er-diagram.png'), dpi=200, bbox_inches='tight')
    plt.close()
    print('er-diagram.png saved')


# ============================================================
# FRONTEND MODULE DIAGRAM (Vue component tree)
# ============================================================
def draw_frontend():
    fig, ax = plt.subplots(1, 1, figsize=(9, 6.5))
    ax.set_xlim(0, 9)
    ax.set_ylim(0, 6.5)
    ax.axis('off')

    def box(x, y, w, h, text, color='#EBF5FB', txt_color=bc):
        r = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.06",
                           facecolor=color, edgecolor=bc, linewidth=1.5, zorder=3)
        ax.add_patch(r)
        ax.text(x+w/2, y+h/2, text, ha='center', va='center', fontproperties=fp_b)

    def arrow(x1, y1, x2, y2):
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle='->', color=bc, lw=1.5), zorder=2)

    # App.vue at top
    box(2.5, 5.5, 4.0, 0.5, 'App.vue (主容器)', '#AED6F1')

    # TopNavBar
    box(2.5, 4.6, 4.0, 0.45, 'TopNavBar (关键词选择 + 时间范围)', '#D5F5E3')
    arrow(4.5, 5.5, 4.5, 5.05)

    # Row 1: Metric cards
    box(0.3, 3.4, 3.6, 0.7, 'AvgHeatCard\n平均热度指数 + 环比 + 迷你折线图', '#FAD7A0')
    box(5.1, 3.4, 3.6, 0.7, 'SentimentCard\n情感分布三色进度条', '#FAD7A0')
    arrow(3.5, 5.5, 2.1, 4.1)
    arrow(5.5, 5.5, 6.9, 4.1)

    # Row 2: WarningPanel (sits between metrics and charts)
    box(0.3, 2.5, 8.4, 0.6, 'WarningPanel — 运营预警区 (实时预警 / 趋势预测 Tab)', '#F1948A')
    ax.text(0.5, 2.75, '热度异常关键词列表 | 暴涨/上升/平稳筛选 | 趋势预测结果', fontproperties=fp_s)
    arrow(4.5, 3.4, 4.5, 3.1)

    # Row 3: Charts
    box(0.3, 1.4, 2.6, 0.7, 'ChannelPieChart\n渠道声量饼图', '#D7BDE2')
    box(3.2, 1.4, 2.6, 0.7, 'TrendChart\n热度趋势 + 预测折线', '#D7BDE2')
    box(6.1, 1.4, 2.6, 0.7, 'WordCloudCard\n热点词云图', '#D7BDE2')
    arrow(4.5, 2.5, 1.6, 2.1)
    arrow(4.5, 2.5, 4.5, 2.1)
    arrow(4.5, 2.5, 7.4, 2.1)

    # Row 4: InfoFeed
    box(0.3, 0.3, 8.4, 0.7, 'InfoFeedCard — 信息流列表 (最新6条, 时间+热度排序)', '#A9DFBF')
    ax.text(0.5, 0.55, '标题 | 来源平台 | 发布时间 | 情感标签 | 热度数值', fontproperties=fp_s)
    arrow(4.5, 1.4, 4.5, 1.0)

    plt.savefig(os.path.join(fig_dir, 'system-modules.png'), dpi=200, bbox_inches='tight')
    plt.close()
    print('system-modules.png saved (frontend modules)')


draw_er()
draw_frontend()
print('All done!')
