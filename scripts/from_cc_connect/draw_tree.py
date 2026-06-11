import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.font_manager import FontProperties
import os

fig_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'figures')
font_path = os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Fonts', 'simhei.ttf')
bc = '#2C3E50'
gray = '#566573'
lgray = '#ABB2B9'

def fp(sz, b=False):
    return FontProperties(fname=font_path, size=sz, weight='bold' if b else 'normal')

fig, ax = plt.subplots(figsize=(16, 10))
ax.set_xlim(0, 16)
ax.set_ylim(0, 10)
ax.axis('off')

def rbox(x, y, w, h, txt, fc='white', ec=bc, lw=1, fs=7, b=False):
    r = FancyBboxPatch((x-w/2, y-h/2), w, h, boxstyle='round,pad=0.03',
                       facecolor=fc, edgecolor=ec, linewidth=lw, zorder=3)
    ax.add_patch(r)
    lines = txt.split('\n')
    for i, ln in enumerate(lines):
        off = (len(lines)-1)*0.12 - i*0.24
        ax.text(x, y+off, ln, ha='center', va='center', fontproperties=fp(fs, b), color=bc)

def hln(x1, x2, y, lw=1, c=gray):
    ax.plot([x1, x2], [y, y], color=c, lw=lw, zorder=1, solid_capstyle='round')

def vln(x, y1, y2, lw=1, c=gray):
    ax.plot([x, x], [y1, y2], color=c, lw=lw, zorder=1, solid_capstyle='round')

# ===== Data =====
data = [
    {
        'n': '数据采集层',
        'm': [
            {'n': 'B站爬虫', 'l': ['关键词搜索获取视频列表', '标题/描述/互动数据', '评论及回复采集']},
            {'n': 'NGA爬虫', 'l': ['论坛搜索获取帖子列表', '帖子标题/正文信息', '帖子回复采集']},
        ]
    },
    {
        'n': '数据传输层',
        'm': [
            {'n': 'Kafka消息\n队列', 'l': ['JSON消息推送至统一主题', '异步解耦采集端与处理端', 'ZooKeeper协调消费位点']},
        ]
    },
    {
        'n': '数据处理层\n(Spark Streaming)',
        'm': [
            {'n': '数据清洗\n与标准化', 'l': ['消息解析与基础校验', '正则去HTML/URL/特殊符号', '时间格式统一标准化', '文本长度过滤(>=5字符)']},
            {'n': '热度计算', 'l': ['等权求和(L+C+Co+F+S)', 'log(1+x)+P95归一化', '指数时间衰减(e^{-t/24})']},
            {'n': '情感分析\n(DeepSeek)', 'l': ['DeepSeek V4 Pro调用', '正向/负向/中性分类', '[-1,1]情感得分映射']},
        ]
    },
    {
        'n': '数据存储层',
        'm': [
            {'n': 'MariaDB', 'l': ['standardized_data核心表', 'content_metrics时序表', 'crawl_queue回访队列表']},
            {'n': 'Redis缓存', 'l': ['API查询结果缓存(5min)', '本地内存缓存(5s)']},
        ]
    },
    {
        'n': '智能分析层',
        'm': [
            {'n': 'XGBoost\n趋势预测', 'l': ['25维特征(滑动窗口聚合)', '上升/平稳/下降三分类']},
            {'n': '异常预警\n系统', 'l': ['实时热度监控', 'lambada驱动波动检测']},
        ]
    },
    {
        'n': '应用展示层',
        'm': [
            {'n': 'Spring Boot\nRESTful API', 'l': ['8个舆情数据/预测接口', '统一ApiResponse响应体', '二级缓存(Redis+内存)']},
            {'n': 'Vue3\n可视化面板', 'l': ['TopNavBar(关键词+时间)', 'AvgHeatCard(热度+环比)', 'SentimentCard(情感分布)', 'WarningPanel(预警+预测)', '图表区(饼图/折线/词云)', 'InfoFeedCard(信息流)']},
        ]
    },
]

# ===== Layout constants =====
N = len(data)
xs = [1.5 + i * 13.0/(N-1) for i in range(N)]  # 1.5, 4.1, 6.7, 9.3, 11.9, 14.5

Y_ROOT = 9.3        # Root center
Y_SUB = 7.6          # Subsystem center
Y_MOD = 5.2          # Module center (first module for multi-module)
Y_MOD_GAP = 0.9      # Gap between modules in same subsystem
Y_LEAF_GAP = 0.42    # Gap between leaves

# ===== Root =====
rbox(8.0, Y_ROOT, 2.0, 0.45, '舆情分析系统', '#1A5276', 'white', 2.5, 14, True)

# Central trunk: root → branch level → each column
BRANCH_Y = Y_SUB + 0.45
root_bot = Y_ROOT - 0.225
sub_top = Y_SUB + 0.225
vln(8.0, BRANCH_Y, root_bot, 1.0, gray)
for cx in xs:
    hln(8.0, cx, BRANCH_Y, 0.8, gray)
    vln(cx, sub_top, BRANCH_Y, 0.8, gray)

# ===== Columns =====
for i, s in enumerate(data):
    cx = xs[i]
    n_m = len(s['m'])

    # Subsystem box
    txt = s['n']
    rbox(cx, Y_SUB, 1.5, 0.45, txt, '#D4E6F1', bc, 1.5, 8, True)

    # Module positions
    if n_m == 1:
        m_ys = [Y_MOD]
    else:
        m_ys = [Y_MOD - j*Y_MOD_GAP for j in range(n_m)]

    # Draw modules
    for j, mod in enumerate(s['m']):
        mj = m_ys[j]
        rbox(cx, mj, 1.5, 0.35, mod['n'], '#EBF5FB', bc, 1, 6.5, True)

        # Connector: subsystem→first module, module→next module
        if j == 0:
            vln(cx, Y_SUB-0.225, mj+0.175, 0.6, gray)
        else:
            vln(cx, m_ys[j-1]-0.175, mj+0.175, 0.6, lgray)

        # Draw leaves
        n_l = len(mod['l'])
        if n_l > 1:
            l_span = (n_l - 1) * Y_LEAF_GAP
            l_ys = [mj - 0.4 - k*l_span/(n_l-1) for k in range(n_l)]
        else:
            l_ys = [mj - 0.4]

        for k, leaf in enumerate(mod['l']):
            lk = l_ys[k]
            rbox(cx, lk, 1.5, 0.22, leaf, '#F8F9FA', lgray, 0.5, 5.5)
            # Connector: module→first leaf, leaf→next leaf
            if k == 0:
                vln(cx, mj-0.175, lk+0.11, 0.4, '#D5D8DC')
            else:
                vln(cx, l_ys[k-1]-0.11, lk+0.11, 0.3, '#D5D8DC')

# Legend
ax.text(0.3, 0.2, '总系统 -> 子系统 -> 模块 -> 具体功能', ha='left', va='center',
        fontproperties=fp(7), color='#999')

plt.savefig(os.path.join(fig_dir, 'system-modules.png'), dpi=200, bbox_inches='tight')
plt.close()
print('system-modules.png saved')
