# -*- coding: utf-8 -*-
"""
NGA 鐖櫕锛坮equests + cloudscraper 鐗堟湰锛?鏇夸唬鏃х増 nga_crawler_playwright.py锛圥laywright 鍗犵敤 ~800MB 鍐呭瓨锛?
浣跨敤锛?  pip install cloudscraper beautifulsoup4 kafka-python

杩愯锛?  python nga_crawler_cloudscraper.py
"""

import json
import os
import random
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urlencode

import cloudscraper
from bs4 import BeautifulSoup


# ============================================================
# Kafka 閰嶇疆锛堜笌 B 绔欑埇铏粺涓€锛?# ============================================================
KAFKA_BOOTSTRAP_SERVERS = "<INTRANET_IP>:9092"
KAFKA_TOPIC = "crawler_data"

# ============================================================
# NGA 娓告垙鏉垮潡 FID 鏄犲皠
# ============================================================
NGA_GAME_FID = {
    "鎵嬫満娓告垙": 863,
    "鐜嬭€呰崳鑰€": 516,
    "鍜屽钩绮捐嫳": 599,
    "鍘熺": 650,
    "宕╁潖鏄熺┕閾侀亾": 818,
    "缁濆尯闆?: 853,
    "鏄庢棩鏂硅垷": -34587507,
    "宕╁潖涓?: 549,
    "澶╂动鏄庢湀鍒€": -23052020,
    "鏃犻檺鏆栨殩": 510373,
    "鑻遍泟鑱旂洘鎵嬫父": 681,
    "閲戦摬閾蹭箣鎴?: 510461,
    "鏄庢棩鏂硅垷缁堟湯鍦?: 846,
    "涓夎娲茶鍔?: 510489,
    "鐏奖蹇嶈€呮墜娓?: -19317848,
    "鐕曚簯鍗佸叚澹?: 510527,
    "閫嗘按瀵掓墜娓?: 510407,
    "姘稿姭鏃犻棿鎵嬫父": -39735775,
    "鍏夐亣": -22495125,
    "绗簲浜烘牸": 607,
    "闃撮槼甯?: 538,
}

# ============================================================
# MongoDB ID 鏄犲皠 鈥斺€?涓?B 绔欑埇铏?store 灞傚吋瀹癸紝鍙瓨 NGA 鍘熷瀛楁
# ============================================================
_NEXT_MONGO_ID = 1000000000


def _generate_mongo_id():
    global _NEXT_MONGO_ID
    _NEXT_MONGO_ID += 1
    return _NEXT_MONGO_ID


class NGACrawlerCloudscraper:
    def __init__(self, keywords=None):
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False,
            },
            delay=5,
        )
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        self.scraper.headers.update(self.headers)

        self.keywords = keywords or [
            "鎵嬫満娓告垙", "鐜嬭€呰崳鑰€", "鍜屽钩绮捐嫳", "鍘熺", "宕╁潖鏄熺┕閾侀亾",
            "缁濆尯闆?, "鏄庢棩鏂硅垷", "宕╁潖涓?, "澶╂动鏄庢湀鍒€", "鏃犻檺鏆栨殩",
            "鑻遍泟鑱旂洘鎵嬫父", "閲戦摬閾蹭箣鎴?, "鏄庢棩鏂硅垷缁堟湯鍦?, "涓夎娲茶鍔?,
            "鐏奖蹇嶈€呮墜娓?, "鐕曚簯鍗佸叚澹?, "閫嗘按瀵掓墜娓?, "姘稿姭鏃犻棿鎵嬫父",
            "鍏夐亣", "绗簲浜烘牸", "闃撮槼甯?,
        ]

        self.base_url = "https://ngabbs.com"
        self.output_dir = "/data/NGA"
        os.makedirs(self.output_dir, exist_ok=True)

        # Kafka 鐢熶骇鑰咃紙鎳掑姞杞斤級
        self._kafka_producer = None
        self.kafka_enabled = False

    # ----------------------------------------------------------
    # Kafka 杈撳嚭锛堜笌 B 绔欑埇铏叡鐢?crawler_data topic锛?    # ----------------------------------------------------------
    def _init_kafka(self):
        if self._kafka_producer is not None:
            return
        try:
            from kafka import KafkaProducer
            self._kafka_producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
                api_version=(0, 10, 1),
                retries=3,
                batch_size=16384,
                linger_ms=10,
                buffer_memory=33554432,
            )
            self.kafka_enabled = True
            print(f"[NGA] Kafka 鐢熶骇鑰呭凡杩炴帴: {KAFKA_BOOTSTRAP_SERVERS}")
        except Exception as e:
            print(f"[NGA] Kafka 杩炴帴澶辫触锛堜笉褰卞搷鐖彇锛? {e}")

    def _send_to_kafka(self, data):
        if self.kafka_enabled and self._kafka_producer:
            try:
                self._kafka_producer.send(KAFKA_TOPIC, value=data)
                self._kafka_producer.flush()
            except Exception as e:
                print(f"[NGA] Kafka 鍙戦€佸け璐? {e}")

    # ----------------------------------------------------------
    # 鏍稿績鐖彇閫昏緫
    # ----------------------------------------------------------
    def run(self):
        self._init_kafka()

        for keyword in self.keywords:
            fid = NGA_GAME_FID.get(keyword)
            if not fid:
                print(f"[NGA] 璺宠繃 {keyword}锛堟棤 FID 鏄犲皠锛?)
                continue

            print(f"\n[NGA] === {keyword} (FID={fid}) ===")
            try:
                self._crawl_keyword(keyword, fid)
            except Exception as e:
                print(f"[NGA] {keyword} 鐖彇鍑洪敊: {e}")

            delay = random.uniform(8, 15)
            print(f"[NGA] 绛夊緟 {delay:.0f}s 鍚庡垏鎹㈠叧閿瘝")
            time.sleep(delay)

        if self._kafka_producer:
            self._kafka_producer.close()

    def _crawl_keyword(self, keyword, fid):
        """鐖彇鍗曚釜鍏抽敭璇嶏紙鍙埇鏈€鏂板彂甯冪殑绗?1 椤碉紝2 灏忔椂绐楀彛锛?""
        page = 1
        while page <= 1:  # 鍙埇绗竴椤?            url = self._build_forum_url(fid, page)
            print(f"[NGA]   page {page}: {url}")

            resp = self.scraper.get(url, timeout=30)
            if resp.status_code != 200:
                print(f"[NGA]   HTTP {resp.status_code}锛岃烦杩?)
                return

            html = resp.text
            if "鎮ㄧ殑璇锋眰杩囦簬棰戠箒" in html or "璇疯緭鍏ラ獙璇佺爜" in html:
                print(f"[NGA]   Cloudflare 鎷︽埅锛岀瓑寰?60s 閲嶈瘯...")
                time.sleep(60)
                continue

            soup = BeautifulSoup(html, "html.parser")
            posts = self._parse_post_list(soup, keyword)
            print(f"[NGA]   瑙ｆ瀽鍒?{len(posts)} 鏉″笘瀛?)

            cutoff = datetime.now() - timedelta(hours=2)
            new_posts = 0
            for post in posts:
                pub_time = post.get("pub_time_parsed")
                if pub_time and pub_time < cutoff:
                    continue  # 瓒呰繃 2 灏忔椂璺宠繃
                new_posts += 1
                # 鏋勯€犱笌 B 绔欑粺涓€鐨勬暟鎹牸寮?                raw_id = f"nga_{post['thread_id']}"
                kafka_msg = {
                    "platform": "nga",
                    "type": "post",
                    "raw_id": raw_id,
                    "author": post.get("author", ""),
                    "title": (post.get("title", "") or "")[:500],
                    "content": (post.get("content", "") or "")[:500],
                    "publish_time": post.get("pub_time_str", ""),
                    "keyword": keyword,
                    "view_count": 0,
                    "like_count": 0,
                    "comment_count": int(post.get("replies", 0)),
                    "coin_count": 0,
                    "favorite_count": 0,
                    "share_count": 0,
                    "danmaku_count": 0,
                    "is_hot_reply": False,
                    "author_fans": 0,
                    "author_level": 0,
                    "author_post_count": 0,
                    "has_image": False,
                    "has_video": False,
                    "board_name": keyword,
                    # crawl_queue 鏍囪鈥斺€旈娆＄埇鍙栨椂鍐欏叆
                    "_crawl_type": "first",
                    "_crawl_time": datetime.now().isoformat(),
                }
                self._send_to_kafka(kafka_msg)
                print(f"[NGA]   -> {raw_id} {post.get('title', '')[:40]}")

            if new_posts == 0 and posts:
                print(f"[NGA]   page {page} 鍏ㄩ儴瓒呰繃 2h锛屽仠姝㈢炕椤?)
                return

            page += 1
            time.sleep(random.uniform(3, 6))

    # ----------------------------------------------------------
    # HTML 瑙ｆ瀽
    # ----------------------------------------------------------
    def _parse_post_list(self, soup, keyword):
        posts = []
        for link in soup.find_all("a", href=re.compile(r"read\.php.+tid=\d+")):
            href = link.get("href", "")
            tid_match = re.search(r"tid=(\d+)", href)
            if not tid_match:
                continue
            title = link.get_text(strip=True)
            if not title or title.isdigit() or "http" in title:
                continue

            thread_id = tid_match.group(1)

            # 鎻愬彇浣滆€呫€佸洖澶嶆暟銆佸彂甯冩椂闂?            author, replies, pub_time_str = self._extract_metadata(link)

            # 鑾峰彇涓昏创鍐呭锛堢敤浜庢儏鎰熷垎鏋愶級
            content = self._fetch_post_content(thread_id)

            pub_time_parsed = self._parse_pub_time(pub_time_str)

            posts.append({
                "thread_id": thread_id,
                "title": title,
                "author": author,
                "replies": replies,
                "content": content,
                "pub_time_str": pub_time_str,
                "pub_time_parsed": pub_time_parsed,
            })

        # 鍘婚噸锛堝悓涓€ tid锛?        seen = set()
        unique = []
        for p in posts:
            if p["thread_id"] not in seen:
                seen.add(p["thread_id"])
                unique.append(p)
        return unique

    def _extract_metadata(self, link):
        author = ""
        replies = "0"
        pub_time = ""

        parent = link.parent
        for _ in range(5):
            if not parent:
                break
            for cls in (".author", ".poster", ".username"):
                el = parent.select_one(cls)
                if el:
                    t = el.get_text(strip=True)
                    if t and not t.isdigit():
                        author = t
                        break
            for cls in (".replies", ".reply", ".posts"):
                el = parent.select_one(cls)
                if el:
                    t = el.get_text(strip=True)
                    if t and t.replace(",", "").isdigit():
                        replies = t.replace(",", "")
                        break
            for cls in (".postdate", ".date", ".time"):
                el = parent.select_one(cls)
                if el:
                    t = el.get_text(strip=True)
                    if t:
                        pub_time = t
                        break
            parent = parent.parent
        return author, replies, pub_time

    def _fetch_post_content(self, thread_id):
        """鑾峰彇涓昏创姝ｆ枃锛堢畝鐭増锛岀敤浜庢儏鎰熷垎鏋愶級"""
        try:
            url = f"{self.base_url}/read.php?tid={thread_id}"
            resp = self.scraper.get(url, timeout=15)
            if resp.status_code != 200:
                return ""
            soup = BeautifulSoup(resp.text, "html.parser")
            for cls in (".postcontent", ".t_f", ".ubbcode"):
                el = soup.select_one(cls)
                if el:
                    txt = el.get_text(strip=True)
                    return txt[:500]
            return ""
        except Exception:
            return ""

    def _parse_pub_time(self, s):
        if not s:
            return None
        now = datetime.now()
        if "浠婂ぉ" in s:
            return now
        if "鏄ㄥぉ" in s:
            return now - timedelta(days=1)
        if "鍓嶅ぉ" in s:
            return now - timedelta(days=2)
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return None
        m = re.match(r"(\d{2})-(\d{2})", s)
        if m:
            try:
                return datetime(now.year, int(m.group(1)), int(m.group(2)))
            except ValueError:
                return None
        return None

    # ----------------------------------------------------------
    # URL 鏋勫缓
    # ----------------------------------------------------------
    def _build_forum_url(self, fid, page):
        if fid > 0:
            return f"{self.base_url}/thread.php?fid={fid}&page={page}"
        else:
            return f"{self.base_url}/thread.php?stid={abs(fid)}&page={page}"


# ============================================================
# 鍏ュ彛
# ============================================================
if __name__ == "__main__":
    crawler = NGACrawlerCloudscraper()
    crawler.run()
