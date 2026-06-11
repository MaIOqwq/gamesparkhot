"""
NGA 娣峰悎鐖櫕锛歅laywright 鍙?cookie + cloudscraper 鐖彇
"""
import json, os, re, time, random
from datetime import datetime, timedelta
from urllib.parse import urlencode

import cloudscraper
from bs4 import BeautifulSoup

KAFKA_BOOTSTRAP_SERVERS = "<INTRANET_IP>:9092"
KAFKA_TOPIC = "crawler_data"

NGA_GAME_FID = {
    "鎵嬫満娓告垙": 863, "鐜嬭€呰崳鑰€": 516, "鍜屽钩绮捐嫳": 599, "鍘熺": 650,
    "宕╁潖鏄熺┕閾侀亾": 818, "缁濆尯闆?: 853, "鏄庢棩鏂硅垷": -34587507,
    "宕╁潖涓?: 549, "澶╂动鏄庢湀鍒€": -23052020, "鏃犻檺鏆栨殩": 510373,
    "鑻遍泟鑱旂洘鎵嬫父": 681, "閲戦摬閾蹭箣鎴?: 510461, "鏄庢棩鏂硅垷缁堟湯鍦?: 846,
    "涓夎娲茶鍔?: 510489, "鐏奖蹇嶈€呮墜娓?: -19317848, "鐕曚簯鍗佸叚澹?: 510527,
    "閫嗘按瀵掓墜娓?: 510407, "姘稿姭鏃犻棿鎵嬫父": -39735775, "鍏夐亣": -22495125,
    "绗簲浜烘牸": 607, "闃撮槼甯?: 538,
}

COOKIE_FILE = "/data/NGA/cloudscraper_cookies.json"


class HybridNGACrawler:
    def __init__(self):
        self.session = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False},
            delay=10,
        )
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        self._load_cookies()

    def _load_cookies(self):
        if os.path.exists(COOKIE_FILE):
            with open(COOKIE_FILE) as f:
                cookies = json.load(f)
            for c in cookies:
                self.session.cookies.set(c["name"], c["value"], domain=c.get("domain", "ngabbs.com"))
            print(f"[NGA] Loaded {len(cookies)} cookies from {COOKIE_FILE}")

    def _save_cookies(self):
        cookies = [{"name": k, "value": v, "domain": "ngabbs.com"}
                   for k, v in self.session.cookies.items()]
        os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
        with open(COOKIE_FILE, "w") as f:
            json.dump(cookies, f, indent=2)
        print(f"[NGA] Saved {len(cookies)} cookies")

    def _refresh_cookies_via_playwright(self):
        """Use Playwright once to get fresh cookies, then save them"""
        print("[NGA] Refreshing cookies via Playwright...")
        try:
            import subprocess
            script = '''
import asyncio, json
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path="/opt/google/chrome/chrome")
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://ngabbs.com/thread.php?fid=516", timeout=30000)
        await page.wait_for_timeout(8000)
        cookies = await context.cookies()
        print(json.dumps(cookies))
        await browser.close()
asyncio.run(main())
'''
            result = subprocess.run(
                ["/pachong/MediaCrawler-main/venv/bin/python3", "-c", script],
                capture_output=True, text=True, timeout=45
            )
            if result.returncode == 0 and result.stdout.strip():
                cookies = json.loads(result.stdout.strip())
                with open(COOKIE_FILE, "w") as f:
                    json.dump(cookies, f, indent=2)
                self._load_cookies()
                print(f"[NGA] Cookie refresh OK, got {len(cookies)} cookies")
                return True
            else:
                print(f"[NGA] Cookie refresh failed: {result.stderr[:200]}")
                return False
        except Exception as e:
            print(f"[NGA] Cookie refresh error: {e}")
            return False

    def _build_forum_url(self, fid, page):
        if fid > 0:
            return f"https://ngabbs.com/thread.php?fid={fid}&page={page}"
        else:
            return f"https://ngabbs.com/thread.php?stid={abs(fid)}&page={page}"

    def _parse_pub_time(self, s):
        if not s: return None
        now = datetime.now()
        if "浠婂ぉ" in s: return now
        if "鏄ㄥぉ" in s: return now - timedelta(days=1)
        if "鍓嶅ぉ" in s: return now - timedelta(days=2)
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            try: return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except: return None
        m = re.match(r"(\d{2})-(\d{2})", s)
        if m:
            try: return datetime(now.year, int(m.group(1)), int(m.group(2)))
            except: return None
        return None

    def _fetch_post_content(self, thread_id):
        try:
            url = f"https://ngabbs.com/read.php?tid={thread_id}"
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200: return ""
            soup = BeautifulSoup(resp.text, "html.parser")
            for cls in (".postcontent", ".t_f", ".ubbcode"):
                el = soup.select_one(cls)
                if el: return el.get_text(strip=True)[:500]
            return ""
        except: return ""

    def crawl_keyword(self, keyword, fid):
        page = 1
        while page <= 1:
            url = self._build_forum_url(fid, page)
            resp = self.session.get(url, timeout=30)
            if resp.status_code != 200:
                print(f"  HTTP {resp.status_code}")
                if "楠岃瘉鐮? in resp.text or "璁垮涓嶈兘鐩存帴璁块棶" in resp.text:
                    print("  Blocked! Need cookie refresh")
                    return False
                return False

            soup = BeautifulSoup(resp.text, "html.parser")
            posts = []
            for link in soup.find_all("a", href=re.compile(r"read\.php.+tid=\d+")):
                href = link.get("href", "")
                tid_match = re.search(r"tid=(\d+)", href)
                if not tid_match: continue
                title = link.get_text(strip=True)
                if not title or title.isdigit() or "http" in title: continue
                tid = tid_match.group(1)
                posts.append({"tid": tid, "title": title})

            seen = set()
            unique = []
            for p in posts:
                if p["tid"] not in seen:
                    seen.add(p["tid"])
                    unique.append(p)

            print(f"  Found {len(unique)} posts on page {page}")
            for post in unique:
                msg = {
                    "platform": "nga", "type": "post",
                    "raw_id": f"nga_{post['tid']}",
                    "author": "", "title": post["title"][:500],
                    "content": "", "publish_time": "",
                    "keyword": keyword,
                    "view_count": 0, "like_count": 0, "comment_count": 0,
                    "coin_count": 0, "favorite_count": 0, "share_count": 0,
                    "danmaku_count": 0, "is_hot_reply": False,
                    "author_fans": 0, "author_level": 0, "author_post_count": 0,
                    "has_image": False, "has_video": False,
                    "board_name": keyword,
                    "_crawl_type": "first",
                    "_crawl_time": datetime.now().isoformat(),
                }
                self._send_to_kafka(msg)
                print(f"  -> nga_{post['tid']} {post['title'][:40]}")

            page += 1
            time.sleep(random.uniform(2, 4))
        return True

    def _send_to_kafka(self, data):
        try:
            from kafka import KafkaProducer
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
                api_version=(0, 10, 1),
            )
            producer.send(KAFKA_TOPIC, value=data)
            producer.flush()
            producer.close()
        except Exception as e:
            print(f"  Kafka send error: {e}")

    def run(self):
        # Initial cookie refresh
        self._refresh_cookies_via_playwright()

        keywords = list(NGA_GAME_FID.keys())
        while True:
            print(f"\n=== NGA Crawl Cycle {datetime.now()} ===")
            for keyword in keywords:
                fid = NGA_GAME_FID[keyword]
                print(f"\n[{keyword}] FID={fid}")
                ok = self.crawl_keyword(keyword, fid)
                if not ok:
                    print("  Crawl failed, refreshing cookies...")
                    self._refresh_cookies_via_playwright()
                    ok = self.crawl_keyword(keyword, fid)
                    if not ok:
                        print(f"  Still failed after cookie refresh, skipping")
                delay = random.uniform(3, 8)
                print(f"  Wait {delay:.0f}s")
                time.sleep(delay)
            print("  Cycle done, wait 120s")
            time.sleep(120)


if __name__ == "__main__":
    HybridNGACrawler().run()
