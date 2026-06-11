#!/usr/bin/env python3
"""
舆情深度分析演示 - 情感归因 + 短语提取 + 作者排行
用法: python3 analysis_demo.py [关键词] [输出.html]
"""
import sys, json, re
from collections import Counter, defaultdict
from datetime import datetime
import pymysql
import jieba
import jieba.analyse

DB = {'host': 'localhost', 'port': 3306, 'user': 'spark', 'password': '123456',
      'database': 'standardized_data', 'charset': 'utf8mb4'}

STOP_WORDS = set('''
的 了 在 是 我 有 和 就 不 人 都 一 一个 上 也 很 到 说 要 去 你
会 着 没有 看 自己 这 他 她 它 们 那 些 什么 而 为 所以 因为
但 但是 可以 这个 那个 如果 虽然 然而 之 与 及 或 被 把 从
让 对 向 往 在 以 将 已 已经 还 又 再 才 就 能 能够 可能
应该 需要 想 想要 觉得 知道 认为 表示 称 说 称 表示 透露
以及 和 且 而且 并且 更 更加 最 非常 比较 很 特别 真 非常
多 少 大 小 好 坏 高 低 新 旧 前 后 左 右 中 内 外 上 下
来 去 进 出 过 回 开 关 到 起 走 跑 跳 飞 吃 喝 玩 买 卖
用 做 作 打 拍 写 读 听 看 说 讲 唱 画 建 造 种 养 学 教
像 如 比 跟 同 一样 似的 一般 吧 呢 吗 啊 呀 哦 嗯 哈哈
'''.split())

# 游戏领域自定义词典
GAME_WORDS = set('''
王者荣耀 英雄联盟 原神 明日方舟 崩坏 星穹铁道 金铲铲 鸣潮 绝区零
新英雄 版本 更新 皮肤 限定 传说 史诗 典藏 荣耀典藏 无双 珍品
削弱 加强 增强 平衡 调整 重做 优化 修复 上线 上线了 上线吗
匹配 机制 排位 巅峰赛 王者局 星耀 钻石 青铜 白银 黄金 铂金
ELO 连胜 连败 连跪 暴击 伤害 技能 大招 被动 铭文 出装 装备
野区 打野 中路 边路 辅助 射手 坦克 法师 战士 刺客
氪金 充值 点券 首充 月卡 战令 赛季 战令皮肤
手感 特效 建模 原画 立绘 海报 语音 台词 音效 配乐
回城 击败 拖尾 天幕 个性按键 播报 表情 头像框
主播 职业选手 KPL 赛事 战队 决赛 冠军
脚本 外挂 演员 摆烂 挂机 举报 信誉分 禁赛 封号
'''.split())

for w in GAME_WORDS:
    jieba.add_word(w)


def clean_text(text):
    if not text: return ''
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'[^一-鿿\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def fetch_data(keyword, limit=5000):
    conn = pymysql.connect(**DB)
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("""
                SELECT author, content_clean, sentiment_score, hot_raw, hot_score,
                       like_count, comment_count, platform, publish_time, title_clean
                FROM standardized_data
                WHERE keyword = %s AND content_clean IS NOT NULL AND content_clean != ''
                ORDER BY publish_time DESC LIMIT %s
            """, (keyword, limit))
            return cur.fetchall()
    finally:
        conn.close()


def segment(text):
    words = jieba.cut(text)
    return [w.strip() for w in words if len(w.strip()) >= 2 and w.strip() not in STOP_WORDS]


def phrase_extraction(rows):
    """用 TF-IDF 提取关键词，用 PMI 提取短语"""
    all_text = []
    pos_text = []
    neg_text = []
    for r in rows:
        text = clean_text(r.get('content_clean', ''))
        if len(text) < 10: continue
        all_text.append(text)
        if r.get('sentiment_score', 0) > 0.2:
            pos_text.append(text)
        elif r.get('sentiment_score', 0) < -0.2:
            neg_text.append(text)

    # TF-IDF 关键词
    full_text = '\n'.join(all_text)
    tfidf = jieba.analyse.extract_tags(full_text, topK=60, withWeight=True)

    pos_full = '\n'.join(pos_text) if pos_text else ''
    neg_full = '\n'.join(neg_text) if neg_text else ''

    # 从正/负面文本分别提取词频
    pos_words = []
    for t in pos_text:
        pos_words.extend(segment(t))
    neg_words = []
    for t in neg_text:
        neg_words.extend(segment(t))

    pos_counter = Counter(pos_words)
    neg_counter = Counter(neg_words)
    total_counter = Counter()
    for t in all_text:
        total_counter.update(segment(t))

    # 计算情感偏向度 (词语在正/负面中出现的倾向)
    word_sentiment_bias = {}
    for word, total in total_counter.most_common(200):
        pc = pos_counter.get(word, 0)
        nc = neg_counter.get(word, 0)
        if pc + nc < 3: continue
        bias = (pc - nc) / (pc + nc)  # -1 到 1
        word_sentiment_bias[word] = {'bias': round(bias, 3), 'pos': pc, 'neg': nc, 'total': total}

    return {
        'tfidf': [(w, round(s, 4)) for w, s in tfidf[:40]],
        'pos_words': pos_counter.most_common(30),
        'neg_words': neg_counter.most_common(30),
        'sentiment_bias': sorted(word_sentiment_bias.items(), key=lambda x: abs(x[1]['bias']), reverse=True)[:50],
    }


def author_ranking(rows):
    """作者排行：按发帖数、总热度、平均热度"""
    authors = defaultdict(lambda: {'posts': 0, 'total_hot': 0, 'platforms': set(), 'total_likes': 0, 'total_comments': 0})

    for r in rows:
        author = r.get('author', '').strip()
        if not author: continue
        a = authors[author]
        a['posts'] += 1
        a['total_hot'] += r.get('hot_raw', 0) or 0
        a['total_likes'] += r.get('like_count', 0) or 0
        a['total_comments'] += r.get('comment_count', 0) or 0
        a['platforms'].add('B站' if r.get('platform') == 1 else 'NGA')

    def rank_authors(rows, key):
        return sorted(rows, key=lambda x: x[1][key], reverse=True)[:20]

    return {
        'by_posts': [(a, d['posts'], len(d['platforms']), round(d['total_hot']/d['posts'], 2), d['total_hot'])
                     for a, d in rank_authors(authors.items(), 'posts')],
        'by_hot': [(a, round(d['total_hot'], 2), d['posts'], round(d['total_hot']/d['posts'], 2))
                   for a, d in rank_authors(authors.items(), 'total_hot')],
        'by_avg': [(a, round(d['total_hot']/d['posts'], 2), d['posts'], round(d['total_hot'], 2))
                   for a, d in sorted(authors.items(), key=lambda x: x[1]['total_hot']/(x[1]['posts'] or 1), reverse=True)
                   if d['posts'] >= 3][:20],
    }


def generate_html(keyword, phrase_data, author_data, stats):
    """生成独立的 HTML 演示页面"""
    tfidf_words = phrase_data['tfidf']
    bias_words = phrase_data['sentiment_bias'][:30]
    pos_words = phrase_data['pos_words'][:15]
    neg_words = phrase_data['neg_words'][:15]

    # TF-IDF 词云数据 (JSON)
    wordcloud_data = json.dumps([{'name': w, 'value': int(s*10000)} for w, s in tfidf_words[:40]])

    # 情感偏向图数据
    bias_chart_data = json.dumps([
        {'name': w, 'value': round(d['bias'] * 100)} for w, d in bias_words
    ])

    # 作者表格
    author_rows = ''
    for i, (name, val, posts, extra) in enumerate(author_data['by_hot'][:15]):
        author_rows += f'''
        <tr>
            <td class="rank">{i+1}</td>
            <td class="author-name">{name}</td>
            <td>{val}</td>
            <td>{posts}</td>
            <td>{extra}</td>
        </tr>'''

    # TF-IDF 关键词标签
    tfidf_tags = ''
    colors = ['#ef4444', '#f97316', '#eab308', '#22c55e', '#3b82f6', '#8b5cf6', '#ec4899']
    for i, (w, s) in enumerate(tfidf_words[:30]):
        size = 12 + s * 40
        color = colors[i % len(colors)]
        tfidf_tags += f'<span style="font-size:{size:.0f}px;color:{color};margin:4px;display:inline-block;opacity:0.85">{w}</span>'

    # 正负面词对比
    pos_tags = ''.join([f'<span class="tag pos-tag">{w} ({c})</span>' for w, c in pos_words])
    neg_tags = ''.join([f'<span class="tag neg-tag">{w} ({c})</span>' for w, c in neg_words])

    # 情感偏向词条
    bias_rows = ''
    for w, d in bias_words[:25]:
        bias_pct = int((d['bias'] + 1) / 2 * 100)
        bg = f'linear-gradient(to right, #ef4444 {100-bias_pct}%, #e2e8f0 {100-bias_pct}%, #e2e8f0 {bias_pct}%, #22c55e {bias_pct}%)'
        bias_rows += f'''
        <div class="bias-row">
            <span class="bias-word">{w}</span>
            <span class="bias-bar-wrap"><span class="bias-bar" style="background:{bg}"></span></span>
            <span class="bias-val">{d["bias"]:+.2f}</span>
        </div>'''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>舆情深度分析 - {keyword}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f1f5f9; color: #1e293b; line-height: 1.6; }}
.container {{ max-width: 1280px; margin: 0 auto; padding: 24px; }}
.header {{ background: white; border-radius: 16px; padding: 24px 32px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
.header h1 {{ font-size: 24px; color: #0f172a; }}
.header .sub {{ color: #64748b; font-size: 14px; margin-top: 4px; }}
.header .stats {{ display: flex; gap: 32px; margin-top: 16px; }}
.header .stat {{ text-align: center; }}
.header .stat-num {{ font-size: 28px; font-weight: 700; color: #3b82f6; }}
.header .stat-label {{ font-size: 12px; color: #94a3b8; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
.card {{ background: white; border-radius: 16px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
.card-full {{ grid-column: 1 / -1; }}
.card h2 {{ font-size: 16px; color: #0f172a; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 2px solid #f1f5f9; }}
.card h2 .badge {{ font-size: 11px; padding: 2px 8px; border-radius: 999px; margin-left: 8px; font-weight: 500; }}
.badge-green {{ background: #dcfce7; color: #16a34a; }}
.badge-blue {{ background: #dbeafe; color: #2563eb; }}
.badge-red {{ background: #fef2f2; color: #dc2626; }}

/* 词云 */
.cloud-wrap {{ text-align: center; padding: 16px 0; line-height: 1.8; min-height: 200px; }}

/* 标签 */
.tag {{ display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12px; margin: 2px; }}
.pos-tag {{ background: #dcfce7; color: #16a34a; }}
.neg-tag {{ background: #fef2f2; color: #dc2626; }}
.tag-wrap {{ display: flex; flex-wrap: wrap; gap: 2px; }}

/* 情感偏向 */
.bias-row {{ display: flex; align-items: center; gap: 12px; margin-bottom: 6px; font-size: 13px; }}
.bias-word {{ width: 100px; text-align: right; color: #475569; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.bias-bar-wrap {{ flex: 1; height: 8px; background: #f1f5f9; border-radius: 4px; overflow: hidden; }}
.bias-bar {{ display: block; height: 100%; border-radius: 4px; width: 100%; }}
.bias-val {{ width: 48px; font-size: 11px; text-align: center; color: #64748b; flex-shrink: 0; }}

/* 作者表 */
.auth-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.auth-table th {{ text-align: left; padding: 8px 12px; color: #94a3b8; font-weight: 500; font-size: 11px; text-transform: uppercase; background: #f8fafc; }}
.auth-table td {{ padding: 10px 12px; border-top: 1px solid #f1f5f9; }}
.auth-table .rank {{ color: #94a3b8; font-weight: 600; width: 32px; }}
.auth-table .author-name {{ font-weight: 500; color: #1e293b; }}

/* 统计数字 */
.num-row {{ display: flex; gap: 24px; flex-wrap: wrap; }}
.num-item {{ background: #f8fafc; border-radius: 12px; padding: 16px 20px; flex: 1; min-width: 120px; text-align: center; }}
.num-item .num {{ font-size: 24px; font-weight: 700; color: #3b82f6; }}
.num-item .lbl {{ font-size: 11px; color: #94a3b8; margin-top: 2px; }}

.green {{ color: #16a34a; }}
.red {{ color: #dc2626; }}
.gray {{ color: #94a3b8; }}

@media (max-width: 768px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="container">
<div class="header">
    <h1>舆情深度分析演示</h1>
    <div class="sub">关键词: {keyword} | 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 基于真实数据库</div>
    <div class="stats">
        <div class="stat"><div class="stat-num">{stats['total']:,}</div><div class="stat-label">总记录数</div></div>
        <div class="stat"><div class="stat-num">{stats['authors']:,}</div><div class="stat-label">独立作者</div></div>
        <div class="stat"><div class="stat-num">{stats['pos_pct']}%</div><div class="stat-label">正面比例</div></div>
        <div class="stat"><div class="stat-num">{stats['neg_pct']}%</div><div class="stat-label">负面比例</div></div>
    </div>
</div>

<div class="grid">
    <!-- TF-IDF 短语提取 -->
    <div class="card card-full">
        <h2>短语提取 <span class="badge badge-blue">TF-IDF Top 30</span></h2>
        <div class="cloud-wrap">{tfidf_tags}</div>
        <p style="color:#94a3b8;font-size:12px;text-align:center;margin-top:8px">
            基于 jieba TF-IDF 算法，字号越大表示在该关键词下越具代表性
        </p>
    </div>

    <!-- 情感归因：正负面词对比 -->
    <div class="card">
        <h2>正面关联词 <span class="badge badge-green">sentiment &gt; 0.2</span></h2>
        <div class="tag-wrap">{pos_tags}</div>
    </div>
    <div class="card">
        <h2>负面关联词 <span class="badge badge-red">sentiment &lt; -0.2</span></h2>
        <div class="tag-wrap">{neg_tags}</div>
    </div>

    <!-- 情感偏向度 -->
    <div class="card card-full">
        <h2>词语情感偏向度 <span class="badge badge-blue">+1.0 = 完全正面, -1.0 = 完全负面</span></h2>
        <div style="padding: 0 12px;">
            <div class="bias-row" style="font-size:10px;color:#94a3b8;margin-bottom:8px">
                <span class="bias-word">← 负面</span>
                <span class="bias-bar-wrap"></span>
                <span class="bias-val">正面 →</span>
            </div>
            {bias_rows}
        </div>
    </div>

    <!-- 作者排行 -->
    <div class="card card-full">
        <h2>高影响力作者 <span class="badge badge-green">按总热度排序</span></h2>
        <div style="overflow-x:auto;">
        <table class="auth-table">
            <thead><tr>
                <th>#</th><th>作者</th><th>总热度</th><th>发帖数</th><th>平均热度</th>
            </tr></thead>
            <tbody>{author_rows}</tbody>
        </table>
        </div>
        <p style="color:#94a3b8;font-size:11px;margin-top:12px">
            注：B站作者粉丝/等级字段当前采集为空，排行基于发帖数+热度值。加入粉丝数可进一步提升排名准确度。
        </p>
    </div>
</div>
</div>
</body>
</html>'''
    return html


def main():
    keyword = sys.argv[1] if len(sys.argv) > 1 else '王者荣耀'
    output = sys.argv[2] if len(sys.argv) > 2 else f'analysis_{keyword}.html'

    print(f"Fetching data for: {keyword}")
    rows = fetch_data(keyword)

    print(f"  Total rows: {len(rows)}")

    # 统计
    total = len(rows)
    pos_count = sum(1 for r in rows if (r.get('sentiment_score') or 0) > 0.2)
    neg_count = sum(1 for r in rows if (r.get('sentiment_score') or 0) < -0.2)
    authors = set(r.get('author', '').strip() for r in rows if r.get('author', '').strip())
    stats = {
        'total': total, 'authors': len(authors),
        'pos_pct': round(pos_count / total * 100, 1) if total > 0 else 0,
        'neg_pct': round(neg_count / total * 100, 1) if total > 0 else 0,
    }

    print("  Extracting phrases...")
    phrase_data = phrase_extraction(rows)

    print("  Ranking authors...")
    author_data = author_ranking(rows)

    print("  Generating HTML...")
    html = generate_html(keyword, phrase_data, author_data, stats)

    with open(output, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Done: {output} ({len(html):,} bytes)")


if __name__ == '__main__':
    main()
