"""
API Bridge Service
Provides ALL backend endpoints by querying the DB directly.
Replaces the need to deploy the Spring Boot backend.
  - /api/opinion/metrics
  - /api/opinion/trend
  - /api/opinion/channel
  - /api/opinion/words
  - /api/opinion/list
  - /api/opinion/warnings
  - /api/opinion/sentiment-timeline
  - /api/predict/trend (proxies to local predict_service)
"""
import math
import os
import re
from datetime import datetime, timedelta

import numpy as np
import pymysql
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

DB_HOST = os.getenv("DB_HOST", "<SERVER_IP>")
DB_USER = os.getenv("DB_USER", "spark")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "standardized_data")
PREDICT_URL = os.getenv("PREDICT_URL", "http://127.0.0.1:5001")

# label map
SENTIMENT_LABELS = {0: "positive", 1: "neutral", 2: "negative"}  # noqa


def get_db():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, charset="utf8mb4",
        connect_timeout=5,
    )


def time_filter_clause(time_range):
    """Build SQL time filter from time range string."""
    if time_range == "all":
        return "1=1"
    mapping = {
        "1d": "NOW() - INTERVAL 1 DAY",
        "3d": "NOW() - INTERVAL 3 DAY",
        "7d": "NOW() - INTERVAL 7 DAY",
        "1m": "NOW() - INTERVAL 1 MONTH",
        "3m": "NOW() - INTERVAL 3 MONTH",
        "6m": "NOW() - INTERVAL 6 MONTH",
        "1y": "NOW() - INTERVAL 1 YEAR",
    }
    if time_range in mapping:
        return f"created_at >= {mapping[time_range]}"
    return f"created_at >= {mapping.get('7d')}"


def time_bin_format(time_range):
    """Return the SQL format string for time bucketing."""
    if time_range in ("1d", "3d", "7d"):
        return "'%%Y-%%m-%%d %%H:00'"  # hourly
    elif time_range in ("1m", "3m"):
        return "'%%Y-%%m-%%d'"  # daily
    else:
        return "'%%Y-%%m-%%d'"  # daily for longer ranges


@app.route('/api/opinion/metrics', methods=['GET'])
def get_metrics():
    keyword = request.args.get('keyword', '')
    time_range = request.args.get('timeRange', '7d')
    tf = time_filter_clause(time_range)

    conn = get_db()
    cur = conn.cursor()
    try:
        # average hot score (use hot_norm)
        if keyword:
            cur.execute(f"SELECT AVG(hot_norm) FROM standardized_data WHERE keyword=%s AND {tf}", (keyword,))
        else:
            cur.execute(f"SELECT AVG(hot_norm) FROM standardized_data WHERE {tf}")
        avg_hot = cur.fetchone()[0] or 0

        # hot index change: compare to first half vs second half of the period
        hot_index_change = 0.0

        # sentiment distribution
        if keyword:
            cur.execute(f"SELECT sentiment_score FROM standardized_data WHERE keyword=%s AND {tf} AND sentiment_score IS NOT NULL", (keyword,))
        else:
            cur.execute(f"SELECT sentiment_score FROM standardized_data WHERE {tf} AND sentiment_score IS NOT NULL")
        scores = [r[0] for r in cur.fetchall() if r[0] is not None]
        total = len(scores)
        if total > 0:
            pos = sum(1 for s in scores if s > 0.2)
            neg = sum(1 for s in scores if s < -0.2)
            neu = total - pos - neg
        else:
            pos = neu = neg = 0

        # trend data (aggregated over time)
        if time_range in ("1d", "3d", "7d"):
            group_fmt = "'%%Y-%%m-%%d %%H:00'"
        else:
            group_fmt = "'%%Y-%%m-%%d'"

        if keyword:
            cur.execute(f"SELECT DATE_FORMAT(created_at, {group_fmt}) as tb, SUM(hot_norm) FROM standardized_data WHERE keyword=%s AND {tf} GROUP BY tb ORDER BY tb", (keyword,))
        else:
            cur.execute(f"SELECT DATE_FORMAT(created_at, {group_fmt}) as tb, SUM(hot_norm) FROM standardized_data WHERE {tf} GROUP BY tb ORDER BY tb")
        trend_rows = cur.fetchall()
        trend_data = [float(r[1]) if r[1] is not None else 0 for r in trend_rows]

        # channel ratio
        if keyword:
            cur.execute(f"SELECT platform, COUNT(*) as cnt FROM standardized_data WHERE keyword=%s AND {tf} GROUP BY platform", (keyword,))
        else:
            cur.execute(f"SELECT platform, COUNT(*) as cnt FROM standardized_data WHERE {tf} GROUP BY platform")
        plat_rows = cur.fetchall()
        total_plat = sum(r[1] for r in plat_rows) or 1
        social = sum(r[1] for r in plat_rows if r[0] == 1)  # platform 1 = B站 (social media)
        trad = sum(r[1] for r in plat_rows if r[0] == 0)  # platform 0 = NGA (forum/traditional)

        return jsonify({
            'code': 200, 'message': 'success', 'data': {
                'averageHotIndex': round(float(avg_hot), 2),
                'hotIndexChange': round(hot_index_change, 1),
                'sentimentRatio': {
                    'positive': pos,
                    'neutral': neu,
                    'negative': neg,
                },
                'socialMediaRatio': round(social / total_plat * 100, 1),
                'traditionalMediaRatio': round(trad / total_plat * 100, 1),
                'trendData': [round(float(t), 2) for t in trend_data],
            }
        })
    finally:
        cur.close()
        conn.close()


@app.route('/api/opinion/trend', methods=['GET'])
def get_trend():
    keyword = request.args.get('keyword', '')
    time_range = request.args.get('timeRange', '7d')
    tf = time_filter_clause(time_range)

    conn = get_db()
    cur = conn.cursor()
    try:
        if time_range in ("1d", "3d", "7d"):
            group_fmt = "'%%Y-%%m-%%d %%H:00'"
        else:
            group_fmt = "'%%Y-%%m-%%d'"

        if keyword:
            cur.execute(f"SELECT DATE_FORMAT(created_at, {group_fmt}) as tb, SUM(hot_norm) FROM standardized_data WHERE keyword=%s AND {tf} GROUP BY tb ORDER BY tb", (keyword,))
        else:
            cur.execute(f"SELECT DATE_FORMAT(created_at, {group_fmt}) as tb, SUM(hot_norm) FROM standardized_data WHERE {tf} GROUP BY tb ORDER BY tb")
        rows = cur.fetchall()
        data = [{'date': str(r[0]), 'value': round(float(r[1]), 2)} for r in rows if r[1] is not None]
        return jsonify({'code': 200, 'message': 'success', 'data': data})
    finally:
        cur.close()
        conn.close()


@app.route('/api/opinion/channel', methods=['GET'])
def get_channel():
    keyword = request.args.get('keyword', '')
    time_range = request.args.get('timeRange', '7d')
    tf = time_filter_clause(time_range)

    conn = get_db()
    cur = conn.cursor()
    try:
        if keyword:
            cur.execute(f"SELECT platform, COUNT(*) as cnt FROM standardized_data WHERE keyword=%s AND {tf} GROUP BY platform", (keyword,))
        else:
            cur.execute(f"SELECT platform, COUNT(*) as cnt FROM standardized_data WHERE {tf} GROUP BY platform")
        rows = cur.fetchall()
        total = sum(r[1] for r in rows) or 1
        plat_names = {0: 'NGA', 1: 'B站', 2: 'NGA'}
        data = [{'channel': plat_names.get(r[0], f'平台{r[0]}'), 'value': round(r[1] / total * 100, 1)} for r in rows]
        return jsonify({'code': 200, 'message': 'success', 'data': data})
    finally:
        cur.close()
        conn.close()


@app.route('/api/opinion/words', methods=['GET'])
def get_words():
    keyword = request.args.get('keyword', '')
    time_range = request.args.get('timeRange', '7d')
    tf = time_filter_clause(time_range)

    conn = get_db()
    cur = conn.cursor()
    try:
        if keyword:
            cur.execute(f"SELECT content_clean FROM standardized_data WHERE keyword=%s AND {tf} AND content_clean IS NOT NULL LIMIT 500", (keyword,))
        else:
            cur.execute(f"SELECT content_clean FROM standardized_data WHERE {tf} AND content_clean IS NOT NULL LIMIT 500")
        texts = [r[0] for r in cur.fetchall() if r[0]]

        # Simple word frequency (Chinese word segmentation not available, use char bigrams + simple splitting)
        word_freq = {}
        # Split on common delimiters
        for text in texts:
            # simple word extraction: get 2-4 char segments via basic splitting
            parts = re.split(r'[\s,，。！？、；：""''（）\(\)【】\[\]]+', str(text))
            for p in parts:
                p = p.strip()
                if 2 <= len(p) <= 20:
                    word_freq[p] = word_freq.get(p, 0) + 1

        # Also extract meaningful single chars (Chinese only)
        for text in texts:
            chars = list(str(text))
            # bigrams
            for i in range(len(chars) - 1):
                bigram = chars[i] + chars[i+1]
                if all('一' <= c <= '鿿' for c in bigram):
                    word_freq[bigram] = word_freq.get(bigram, 0) + 1

        sorted_words = sorted(word_freq.items(), key=lambda x: -x[1])[:80]
        max_freq = max([w[1] for w in sorted_words]) if sorted_words else 1
        data = [{'word': w[0], 'weight': round(w[1] / max_freq * 100)} for w in sorted_words]
        return jsonify({'code': 200, 'message': 'success', 'data': data})
    finally:
        cur.close()
        conn.close()


@app.route('/api/opinion/list', methods=['GET'])
def get_info_list():
    keyword = request.args.get('keyword', '')
    time_range = request.args.get('timeRange', '7d')
    tf = time_filter_clause(time_range)

    conn = get_db()
    cur = conn.cursor()
    try:
        if keyword:
            cur.execute(f"SELECT id, title_clean, platform, created_at, sentiment_score, hot_norm FROM standardized_data WHERE keyword=%s AND {tf} ORDER BY hot_norm DESC LIMIT 50", (keyword,))
        else:
            cur.execute(f"SELECT id, title_clean, platform, created_at, sentiment_score, hot_norm FROM standardized_data WHERE {tf} ORDER BY hot_norm DESC LIMIT 50")
        rows = cur.fetchall()
        data = []
        for r in rows:
            sent = 'neutral'
            if r[4] is not None:
                if r[4] > 0.2:
                    sent = 'positive'
                elif r[4] < -0.2:
                    sent = 'negative'
            plat_name = 'NGA' if r[2] == 0 else 'B站'
            data.append({
                'id': r[0],
                'title': r[1] or '(无标题)',
                'source': plat_name,
                'time': r[3].strftime('%Y-%m-%d %H:%M') if r[3] else '',
                'sentiment': sent,
                'hotValue': round(float(r[5]), 2) if r[5] else 0,
            })
        return jsonify({'code': 200, 'message': 'success', 'data': data})
    finally:
        cur.close()
        conn.close()


@app.route('/api/opinion/warnings', methods=['GET'])
def get_warnings():
    time_range = request.args.get('timeRange', '7d')
    tf = time_filter_clause(time_range)

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT DISTINCT keyword FROM standardized_data")
        all_keywords = [r[0] for r in cur.fetchall()]

        warnings = []
        for kw in all_keywords:
            # current period avg
            cur.execute(f"SELECT AVG(hot_norm) FROM standardized_data WHERE keyword=%s AND {tf}", (kw,))
            current_avg = cur.fetchone()[0] or 0

            # current total hot
            cur.execute(f"SELECT SUM(hot_norm) FROM standardized_data WHERE keyword=%s AND {tf}", (kw,))
            current_total = cur.fetchone()[0] or 0

            # Get hourly averages for the last 7 days and compare today vs yesterday
            cur.execute("""
                SELECT DATE_FORMAT(created_at, '%%Y-%%m-%%d') as day, AVG(hot_norm)
                FROM standardized_data
                WHERE keyword=%s AND created_at >= NOW() - INTERVAL 7 DAY
                GROUP BY day ORDER BY day
            """, (kw,))
            day_rows = cur.fetchall()
            day_avgs = [float(r[1]) for r in day_rows if r[1] is not None]

            if len(day_avgs) >= 2:
                today_avg = day_avgs[-1]
                yesterday_avg = day_avgs[-2]
                if yesterday_avg > 0.001:
                    change_rate = (today_avg - yesterday_avg) / yesterday_avg
                    change_rate = max(-1, min(3, change_rate))  # clamp reasonable range
                elif today_avg > 0.001:
                    change_rate = 1.0  # new activity
                else:
                    change_rate = 0.0
            else:
                change_rate = 0.0

            # Determine level and trend
            if change_rate > 1.0 and current_avg > 0.2:
                level = 'danger'
                trend = '暴涨'
                trend_code = 4
                msg = f'热度暴涨 {change_rate:.0%}，当前热度 {current_avg:.2f}'
            elif change_rate > 0.5 and current_avg > 0.15:
                level = 'warning'
                trend = '上升'
                trend_code = 3
                msg = f'热度显著上升 {change_rate:.0%}'
            elif change_rate < -0.5 and current_avg < 0.3:
                level = 'danger'
                trend = '暴跌'
                trend_code = 0
                msg = f'热度暴跌 {change_rate:.0%}，当前热度仅 {current_avg:.2f}'
            elif change_rate < -0.3:
                level = 'warning'
                trend = '下降'
                trend_code = 1
                msg = f'热度下降 {change_rate:.0%}'
            else:
                level = 'normal'
                trend = '平稳'
                trend_code = 2
                msg = f'热度平稳，变化 {change_rate:.1%}'

            warnings.append({
                'keyword': kw,
                'currentHot': round(current_total, 2),
                'changeRate': round(change_rate, 4),
                'trend': trend,
                'trendCode': trend_code,
                'confidence': 0.0,
                'level': level,
                'message': msg,
            })

        # Sort: danger first, then warning, then normal; within same level by abs(changeRate) desc
        level_order = {'danger': 0, 'warning': 1, 'normal': 2}
        warnings.sort(key=lambda w: (level_order.get(w['level'], 3), -abs(w['changeRate'])))


        return jsonify({'code': 200, 'message': 'success', 'data': warnings})
    finally:
        cur.close()
        conn.close()


@app.route('/api/opinion/sentiment-timeline', methods=['GET'])
def get_sentiment_timeline():
    keyword = request.args.get('keyword', '')
    time_range = request.args.get('timeRange', '7d')
    tf = time_filter_clause(time_range)

    conn = get_db()
    cur = conn.cursor()
    try:
        if time_range in ("1d", "3d", "7d"):
            group_fmt = "'%%Y-%%m-%%d %%H:00'"
        else:
            group_fmt = "'%%Y-%%m-%%d'"

        if keyword:
            cur.execute(f"SELECT DATE_FORMAT(created_at, {group_fmt}) as tb, sentiment_score FROM standardized_data WHERE keyword=%s AND {tf} AND sentiment_score IS NOT NULL ORDER BY tb", (keyword,))
        else:
            cur.execute(f"SELECT DATE_FORMAT(created_at, {group_fmt}) as tb, sentiment_score FROM standardized_data WHERE {tf} AND sentiment_score IS NOT NULL ORDER BY tb")

        rows = cur.fetchall()
        # Group by time bucket
        buckets = {}
        for tb, score in rows:
            if tb not in buckets:
                buckets[tb] = {'positive': 0, 'neutral': 0, 'negative': 0}
            if score > 0.2:
                buckets[tb]['positive'] += 1
            elif score < -0.2:
                buckets[tb]['negative'] += 1
            else:
                buckets[tb]['neutral'] += 1

        data = sorted(
            [{'date': str(k), **v} for k, v in buckets.items()],
            key=lambda x: x['date']
        )
        return jsonify({'code': 200, 'message': 'success', 'data': data})
    finally:
        cur.close()
        conn.close()


@app.route('/api/predict/trend', methods=['GET'])
def predict_trend_proxy():
    """Proxy to the local prediction service."""
    keyword = request.args.get('keyword', '')
    try:
        resp = requests.get(f"{PREDICT_URL}/api/predict/trend?keyword={keyword}", timeout=10)
        return jsonify(resp.json())
    except requests.exceptions.ConnectionError:
        # Fallback: return default
        return jsonify({
            'code': 200, 'message': 'success', 'data': {
                'keyword': keyword,
                'trend_code': 2, 'trend_label': '平稳',
                'confidence': 0.0, 'predicted_hot': 0,
                'current_hot': 0, 'change_rate': 0,
            }
        })


@app.route('/api/predict/trend/batch', methods=['POST'])
def predict_batch_proxy():
    try:
        resp = requests.post(f"{PREDICT_URL}/api/predict/trend/batch", json=request.get_json(), timeout=30)
        return jsonify(resp.json())
    except requests.exceptions.ConnectionError:
        return jsonify({'code': 500, 'message': 'Prediction service not available', 'data': None}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'api-bridge'})


if __name__ == '__main__':
    port = int(os.getenv("PORT", 8080))
    print(f"Starting API bridge on port {port}")
    print(f"Proxying predictions to {PREDICT_URL}")
    app.run(host='0.0.0.0', port=port, debug=False)
