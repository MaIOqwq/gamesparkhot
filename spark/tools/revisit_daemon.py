# -*- coding: utf-8 -*-
"""
爬虫回访脚本

职责：
  1. 扫描 crawl_queue 中待回访的内容
  2. 用 HTTP 请求获取当前评论数/互动数
  3. 计算 λ = (新值 - 旧值) / 间隔小时数
  4. 写入 content_metrics（时序数据）
  5. 更新 crawl_queue（下次回访时间、λ 级别）
  6. 如果内容仍有活跃度，推回访任务到爬虫增量拉取新评论

运行方式：
  python revisit_daemon.py          # 单次运行
  python revisit_daemon.py --loop   # 持续循环（每 5 分钟一次）
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

import pymysql
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============================================================
# 数据库配置
# ============================================================
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "spark")
DB_PASSWORD = os.getenv("DB_PASSWORD", "your_db_password")
DB_NAME = os.getenv("DB_NAME", "standardized_data")

# ============================================================
# λ 阈值配置（与系统改进方案.md 一致）
# ============================================================
# B站
BILI_LAMBDA_THRESHOLDS = [
    (30,  "爆款", 15),     # λ ≥ 30 → 15分钟回访
    (5,   "热门", 60),     # λ ≥ 5  → 1小时
    (1,   "中等", 180),    # λ ≥ 1  → 3小时
    (0.1, "低活", 720),    # λ ≥ 0.1 → 12小时
    (0,   "沉寂", -1),     # λ < 0.1 → 停止
]

# NGA
NGA_LAMBDA_THRESHOLDS = [
    (20, "爆款", 15),
    (5,  "热门", 60),
    (1,  "中等", 180),
    (0.1,"低活", 720),
    (0,  "沉寂", -1),
]

# ============================================================
# HTTP 会话（带重试）
# ============================================================
def _make_session():
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=1, status_forcelist=[502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json,text/html,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    return s


# ============================================================
# 平台 API 调用
# ============================================================
def fetch_bili_stats(session, bvid: str):
    """获取 B 站视频当前互动数据"""
    try:
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        resp = session.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("code") != 0:
            return None
        stat = data["data"]["stat"]
        return {
            "view_count": stat.get("view", 0),
            "like_count": stat.get("like", 0),
            "comment_count": stat.get("reply", 0),
            "coin_count": stat.get("coin", 0),
            "favorite_count": stat.get("favorite", 0),
            "share_count": stat.get("share", 0),
            "hot_raw": sum([
                stat.get("like", 0),
                stat.get("reply", 0),
                stat.get("coin", 0),
                stat.get("favorite", 0),
                stat.get("share", 0),
            ]),
        }
    except Exception as e:
        print(f"  [B站API] 请求失败: {e}")
        return None


def fetch_nga_stats(session, tid: str):
    """获取 NGA 帖子当前回复数（通过搜索页面）"""
    try:
        url = f"https://ngabbs.com/thread.php?tid={tid}"
        resp = session.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        if resp.status_code != 200:
            return None
        import re
        # 从 HTML 中提取回复数
        m = re.search(r"回复数[：:]\s*(\d+)", resp.text)
        if not m:
            m = re.search(r"回复[：:]\s*(\d+)", resp.text)
        reply_count = int(m.group(1)) if m else 0
        return {
            "view_count": 0,
            "like_count": 0,
            "comment_count": reply_count,
            "coin_count": 0,
            "favorite_count": 0,
            "share_count": 0,
            "hot_raw": reply_count,
        }
    except Exception as e:
        print(f"  [NGA API] 请求失败: {e}")
        return None


# ============================================================
# 核心回访逻辑
# ============================================================
def calc_lambda(current_count, last_count, hours_elapsed):
    if hours_elapsed < 0.01:
        return 0.0
    return max(0, (current_count - last_count)) / hours_elapsed


def get_thresholds(platform):
    return BILI_LAMBDA_THRESHOLDS if platform == 1 else NGA_LAMBDA_THRESHOLDS


def classify_lambda(l, platform):
    thresholds = get_thresholds(platform)
    for bound, label, interval_min in thresholds:
        if l >= bound:
            return label, interval_min
    return "沉寂", -1


def run_revisit_cycle(conn):
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    session = _make_session()

    # 查询待回访内容
    cursor.execute("""
        SELECT raw_id, platform, keyword, last_visited, last_comment_count,
               last_like_count, last_hot_raw, visit_count
        FROM crawl_queue
        WHERE status = 'active' AND next_visit <= NOW()
        ORDER BY next_visit ASC
        LIMIT 50
    """)
    items = cursor.fetchall()
    print(f"[回访] 待回访 {len(items)} 条")

    now = datetime.now()

    for item in items:
        raw_id = item["raw_id"]
        platform = item["platform"]
        keyword = item["keyword"]
        last_comment = item["last_comment_count"] or 0
        last_hot = item["last_hot_raw"] or 0.0
        last_visited = item["last_visited"]
        visit_count = item["visit_count"] or 0

        print(f"  -> {raw_id} (平台={'B站' if platform==1 else 'NGA'})")

        # 获取当前数据
        if platform == 1:  # B站 bvid = raw_id (去掉 "bili_" 等前缀)
            bvid = raw_id.replace("bili_", "").replace("bv", "BV")
            if not bvid.startswith("BV"):
                bvid = f"BV{bvid}"
            stats = fetch_bili_stats(session, bvid)
        else:  # NGA
            tid = raw_id.replace("nga_", "")
            stats = fetch_nga_stats(session, tid)

        if stats is None:
            print(f"    API 请求失败，跳过")
            continue

        current_comment = stats["comment_count"]
        current_hot = stats["hot_raw"]
        hours_since = (now - last_visited).total_seconds() / 3600 if last_visited else 1.0
        l = calc_lambda(current_comment, last_comment, hours_since)
        label, interval_min = classify_lambda(l, platform)

        print(f"    评论 {last_comment}->{current_comment}, λ={l:.2f}, 级别={label}")

        # 写入 content_metrics
        cursor.execute("""
            INSERT INTO content_metrics
                (raw_id, platform, captured_at, comment_count, like_count,
                 coin_count, favorite_count, share_count, view_count,
                 hot_raw, hot_score, lambda, revisit_level)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            raw_id, platform, now,
            stats["comment_count"], stats["like_count"],
            stats["coin_count"], stats["favorite_count"],
            stats["share_count"], stats["view_count"],
            current_hot, 0.0, l,
            1 if label in ("爆款", "热门") else (
                2 if label in ("中等",) else 3
            )
        ))

        # 更新 crawl_queue
        if interval_min > 0:
            next_visit = now + timedelta(minutes=interval_min)
            cursor.execute("""
                UPDATE crawl_queue SET
                    last_visited = %s,
                    next_visit = %s,
                    current_lambda = %s,
                    revisit_level = %s,
                    last_comment_count = %s,
                    last_like_count = %s,
                    last_hot_raw = %s,
                    visit_count = visit_count + 1,
                    status = 'active'
                WHERE raw_id = %s
            """, (now, next_visit, l, 1 if label in ("爆款", "热门") else (
                2 if label in ("中等",) else 3 if label in ("低活",) else -1
            ), current_comment, stats.get("like_count", 0),
                current_hot, raw_id))
        else:
            # 沉寂：标记为 dead
            cursor.execute("""
                UPDATE crawl_queue SET
                    last_visited = %s,
                    current_lambda = %s,
                    revisit_level = -1,
                    status = 'dead'
                WHERE raw_id = %s
            """, (now, l, raw_id))

        conn.commit()

        # 活跃内容推送给爬虫——标记需要增量拉新评论
        if label in ("爆款", "热门") and interval_min <= 60:
            print(f"    活跃内容，安排爬虫增量拉取")
            # TODO: 调用爬虫管理 API 触发增量爬取

        time.sleep(1)  # API 限速

    cursor.close()


def get_connection():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, charset="utf8mb4",
        connect_timeout=10, read_timeout=30, write_timeout=30,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="持续循环运行")
    args = parser.parse_args()

    if args.loop:
        print("[回访] 启动守护模式（每 5 分钟扫描一次）")
        while True:
            conn = None
            try:
                conn = get_connection()
                run_revisit_cycle(conn)
            except Exception as e:
                print(f"[回访] 错误: {e.__class__.__name__}: {e}", flush=True)
                import traceback
                traceback.print_exc()
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
            print("[回访] 等待 5 分钟...", flush=True)
            time.sleep(300)
    else:
        conn = get_connection()
        try:
            run_revisit_cycle(conn)
        finally:
            conn.close()


if __name__ == "__main__":
    main()
