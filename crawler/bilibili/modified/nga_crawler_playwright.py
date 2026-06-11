import asyncio
import json
import os
import random
import re
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from confluent_kafka import Producer


class NGACrawlerPlaywright:
    """NGA璁哄潧鐖櫕"""

    def __init__(self, config):
        """鍒濆鍖栫埇铏?""
        self.config = config
        self.cookies = config.get('cookies', {})
        self.keywords = config.get('keywords', [])
        self.base_url = 'https://ngabbs.com'
        self.output_dir = '/data/NGA'
        self.max_posts_per_keyword = 5000
        self.status_file = os.path.join(self.output_dir, 'crawler_status.json')
        self.last_crawl_time_file = os.path.join(self.output_dir, 'last_crawl_time.json')

        # 鍏抽敭璇嶅埌FID鐨勬槧灏?        self.NGA_GAME_FID = {
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
            "楦ｆ疆": 854,
        }

        # 鍒濆鍖栫埇鍙栫姸鎬?        self.current_status = {
            'current_keyword_index': 0,
            'current_page': 1,
            'posts_collected': 0,
            'mode': 'full',  # 'full' 鎴?'incremental'
            'last_crawl_time': None
        }

        # 鍒涘缓杈撳嚭鐩綍
        self._ensure_directory(self.output_dir)

        # Kafka閰嶇疆
        kafka_config = config.get('kafka', {})
        self.kafka_enabled = kafka_config.get('enabled', True)
        self.kafka_bootstrap_servers = kafka_config.get('bootstrap_servers', '<INTRANET_IP>:9092')
        self.kafka_topic = kafka_config.get('topic', 'crawler_data')
        self.kafka_producer = None

    def _ensure_directory(self, directory):
        """纭繚鐩綍瀛樺湪"""
        if not os.path.exists(directory):
            os.makedirs(directory)

    def _init_kafka_producer(self):
        """鍒濆鍖朘afka鐢熶骇鑰?""
        if self.kafka_enabled:
            try:
                self.kafka_producer = Producer({
                    'bootstrap.servers': self.kafka_bootstrap_servers,
                    'client.id': 'nga-crawler',
                    'acks': 'all',
                    'retries': 3,
                    'batch.num.messages': 16384,
                    'linger.ms': 10,
                    'queue.buffering.max.messages': 100000
                })
                print(f"Kafka鐢熶骇鑰呭垵濮嬪寲鎴愬姛: {self.kafka_bootstrap_servers}")
            except Exception as e:
                print(f"Kafka鐢熶骇鑰呭垵濮嬪寲澶辫触: {e}")
                self.kafka_enabled = False

    def _send_to_kafka(self, data, topic):
        """鍙戦€佹暟鎹埌Kafka"""
        if self.kafka_enabled and self.kafka_producer:
            try:
                self.kafka_producer.produce(topic, value=json.dumps(data).encode('utf-8'))
                # 绉婚櫎姣忔鍙戦€佸悗鐨刦lush()锛屾彁楂樻€ц兘
                # self.kafka_producer.flush()
            except Exception as e:
                print(f"鍙戦€佹暟鎹埌Kafka澶辫触: {e}")

    async def run(self):
        """杩愯鐖櫕"""
        browser = None
        context = None
        try:
            start_time = datetime.now()
            print(f"鐖櫕寮€濮嬭繍琛岋紝鏃堕棿: {start_time}")
            print(f"鍏抽敭璇嶆暟閲? {len(self.keywords)}")

            # 鍒濆鍖朘afka鐢熶骇鑰?            self._init_kafka_producer()

            # 鍔犺浇鐖彇鐘舵€?            status_loaded = self.load_status()

            async with async_playwright() as p:
                print("姝ｅ湪鍚姩娴忚鍣?..")
                browser = await self._launch_browser(p)
                context = await browser.new_context()

                if self.cookies:
                    await self._login(context)

                # 棣栨鍏ㄩ噺鐖彇
                print("寮€濮嬮娆″叏閲忕埇鍙?..")
                # 浠庝繚瀛樼殑浣嶇疆缁х画鐖彇
                start_index = self.current_status.get('current_keyword_index', 0)

                for i, keyword in enumerate(self.keywords[start_index:], start=start_index):
                    print(f"\n寮€濮嬪鐞嗗叧閿瘝: {keyword}")
                    # 鏇存柊褰撳墠鍏抽敭璇嶇储寮?                    self.current_status['current_keyword_index'] = i
                    self.current_status['current_page'] = 1
                    self.current_status['posts_collected'] = 0
                    self.current_status['last_crawl_time'] = start_time.isoformat()
                    self.current_status['mode'] = 'full'
                    self.save_status()

                    # 鍔犺浇瀵瑰簲鍏抽敭璇嶇殑tid鍒楄〃
                    recent_tids = self.load_recent_tids(keyword)
                    print(f"宸插姞杞?{len(recent_tids)} 涓渶杩戠殑tid")

                    tids = await self.crawl_forum(context, keyword, start_time, recent_tids)

                    # 淇濆瓨瀵瑰簲鍏抽敭璇嶇殑tid鍒楄〃
                    if tids:
                        self.save_recent_tids(keyword, tids)

                    # 淇濆瓨鐘舵€?                    self.save_status()

                    if i < len(self.keywords) - 1:
                        print("鍒囨崲鍏抽敭璇嶏紝娣诲姞寤惰繜...")
                        await self._random_delay(10, 15)

                # 淇濆瓨鏈€鍚庣埇鍙栨椂闂?                self.save_last_crawl_time()

                # 鐖彇瀹屾垚锛屾竻闄ょ姸鎬?                if os.path.exists(self.status_file):
                    os.remove(self.status_file)
                    print("鍏ㄩ噺鐖彇瀹屾垚锛屽凡娓呴櫎鐘舵€佹枃浠?)

                # 杩涘叆澧為噺鐖彇寰幆锛屾瘡涓ゅ皬鏃剁埇鍙栦竴娆?                print("\n寮€濮嬪閲忕埇鍙栨ā寮忥紝姣忎袱灏忔椂鐖彇涓€娆?..")
                while True:
                    print(f"\n{datetime.now()} - 寮€濮嬪閲忕埇鍙?)

                    # 閲嶇疆鐘舵€?                    self.current_status = {
                        'current_keyword_index': 0,
                        'current_page': 1,
                        'posts_collected': 0,
                        'mode': 'incremental',
                        'last_crawl_time': datetime.now().isoformat()
                    }

                    for i, keyword in enumerate(self.keywords):
                        print(f"\n澶勭悊鍏抽敭璇? {keyword}")
                        # 鏇存柊褰撳墠鍏抽敭璇嶇储寮?                        self.current_status['current_keyword_index'] = i
                        self.current_status['current_page'] = 1
                        self.current_status['posts_collected'] = 0
                        self.current_status['last_crawl_time'] = datetime.now().isoformat()
                        self.save_status()

                        # 鍔犺浇瀵瑰簲鍏抽敭璇嶇殑tid鍒楄〃
                        recent_tids = self.load_recent_tids(keyword)
                        print(f"宸插姞杞?{len(recent_tids)} 涓渶杩戠殑tid")

                        tids = await self.crawl_forum(context, keyword, datetime.now(), recent_tids)

                        # 淇濆瓨瀵瑰簲鍏抽敭璇嶇殑tid鍒楄〃
                        if tids:
                            self.save_recent_tids(keyword, tids)

                        # 淇濆瓨鐘舵€?                        self.save_status()

                        if i < len(self.keywords) - 1:
                            print("鍒囨崲鍏抽敭璇嶏紝娣诲姞寤惰繜...")
                            await self._random_delay(10, 15)

                    # 淇濆瓨鏈€鍚庣埇鍙栨椂闂?                    self.save_last_crawl_time()

                    # 鐖彇瀹屾垚锛屾竻闄ょ姸鎬?                    if os.path.exists(self.status_file):
                        os.remove(self.status_file)
                        print("澧為噺鐖彇瀹屾垚锛屽凡娓呴櫎鐘舵€佹枃浠?)

                    # 绛夊緟涓ゅ皬鏃?                    print(f"\n{datetime.now()} - 澧為噺鐖彇瀹屾垚锛岀瓑寰呬袱灏忔椂鍚庡啀娆＄埇鍙?..")
                    await asyncio.sleep(2 * 60 * 60)  # 涓ゅ皬鏃?        except Exception as e:
            # 鍑洪敊鏃朵繚瀛樼姸鎬?            self.save_status()
            print(f"杩愯鐖櫕鏃跺嚭閿? {e}")
        finally:
            # 纭繚娴忚鍣ㄥ拰涓婁笅鏂囪鍏抽棴
            try:
                if context:
                    await context.close()
                    print("宸插叧闂祻瑙堝櫒涓婁笅鏂?)
                if browser:
                    await browser.close()
                    print("宸插叧闂祻瑙堝櫒")
            except Exception as e:
                print(f"鍏抽棴娴忚鍣ㄦ椂鍑洪敊: {e}")

            # 鍏抽棴Kafka鐢熶骇鑰?            if self.kafka_producer:
                try:
                    # 鍙戦€佹墍鏈夌紦鍐茬殑娑堟伅
                    self.kafka_producer.flush()
                    print("宸插埛鏂癒afka鐢熶骇鑰呯紦鍐插尯")
                    self.kafka_producer.close()
                    print("宸插叧闂璌afka鐢熶骇鑰?)
                except Exception as e:
                    print(f"鍏抽棴Kafka鐢熶骇鑰呮椂鍑洪敊: {e}")

    async def _launch_browser(self, playwright):
        """鍚姩娴忚鍣紝浼樺厛浣跨敤绯荤粺Chrome"""
        try:
            browser = await playwright.chromium.launch(
                executable_path="/usr/bin/google-chrome",
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu"
                ]
            )
            print("浣跨敤绯荤粺Chrome娴忚鍣ㄦ垚鍔?)
        except Exception as e:
            print(f"浣跨敤绯荤粺Chrome澶辫触: {e}锛屽皾璇曚娇鐢≒laywright榛樿娴忚鍣?)
            browser = await playwright.chromium.launch(headless=True)
        return browser

    async def _login(self, context):
        """鐧诲綍NGA璁哄潧"""
        cookie_list = []
        for key, value in self.cookies.items():
            if value:
                cookie_list.append({
                    'name': key,
                    'value': value,
                    'url': self.base_url
                })

        if cookie_list:
            await context.add_cookies(cookie_list)
            print("鐧诲綍涓?..")
            # 娴嬭瘯鐧诲綍鐘舵€?            test_page = await context.new_page()
            await test_page.goto(f'{self.base_url}/')
            await test_page.wait_for_load_state('networkidle')
            test_content = await test_page.content()
            await test_page.close()

            if 'MaIO233' in test_content:
                print("鐧诲綍鎴愬姛")
            else:
                print("鐧诲綍澶辫触锛屽皾璇曠户缁埇鍙?)

    async def crawl_forum(self, context, keyword, start_time, recent_tids):
        """鐩存帴鐖彇瀵瑰簲鏉垮潡鐨勫笘瀛愶紙鏀寔澧為噺鐖彇锛?""
        try:
            # 鑾峰彇瀵瑰簲鐨凢ID
            fid = self.NGA_GAME_FID.get(keyword)
            if not fid:
                print(f"鏈壘鍒板叧閿瘝 '{keyword}' 瀵瑰簲鐨凢ID锛岃烦杩?)
                return []

            found_posts = self.current_status.get('posts_collected', 0)
            page_num = self.current_status.get('current_page', 1)
            collected_tids = []

            # 鍒涘缓鏃堕棿鎴虫枃浠跺す锛堢簿搴︿负澶╋級
            crawl_time = datetime.now().strftime('%Y-%m-%d')
            context_dir, comment_dir = self._create_output_directories(crawl_time)

            # 杩炵画閬囧埌2020骞翠箣鍓嶅笘瀛愮殑璁℃暟
            consecutive_old_posts = 0
            max_consecutive_old_posts = 5

            # 杩炵画绌洪〉闈㈣鏁?            consecutive_empty_pages = 0
            max_consecutive_empty_pages = 3

            while found_posts < self.max_posts_per_keyword:
                # 鏋勫缓鏉垮潡URL
                forum_url = self._build_forum_url(keyword, fid, page_num)

                print(f"璁块棶鏉垮潡: {keyword} (FID: {fid})锛岀 {page_num} 椤?)
                print(f"璁块棶URL: {forum_url}")

                page = None
                try:
                    page = await context.new_page()
                    print("姝ｅ湪璁块棶鏉垮潡椤甸潰...")
                    await page.goto(forum_url)
                    print("绛夊緟椤甸潰鍔犺浇瀹屾垚...")
                    await page.wait_for_load_state('networkidle')
                    print("椤甸潰鍔犺浇瀹屾垚")

                    content = await page.content()
                finally:
                    if page:
                        await page.close()
                        print("宸插叧闂澘鍧楅〉闈?)

                soup = BeautifulSoup(content, 'html.parser')

                # 妫€鏌ユ槸鍚︿负閿欒椤甸潰
                if '浣犲繀椤荤櫥褰曟墠鑳芥煡璇㈡洿鏃╃殑缁撴灉' in content:
                    print("閬囧埌鐧诲綍闄愬埗锛屽仠姝㈢炕椤?)
                    # 鏄惧紡娓呯悊soup瀵硅薄
                    del soup
                    import gc
                    gc.collect()
                    break

                # 鎵惧埌鎵€鏈夊笘瀛愰摼鎺?                all_links = soup.find_all('a', href=re.compile(r'tid=\d+'))
                print(f"鎵惧埌 {len(all_links)} 涓寘鍚玹id鐨勯摼鎺?)

                # 濡傛灉娌℃湁鎵惧埌閾炬帴锛岃鏄庡凡缁忓埌鏈€鍚庝竴椤?                if not all_links:
                    print("鏈壘鍒版洿澶氬笘瀛愶紝鍋滄缈婚〉")
                    # 鏄惧紡娓呯悊soup瀵硅薄
                    del soup
                    import gc
                    gc.collect()
                    break

                # 鏀堕泦褰撳墠椤电殑甯栧瓙
                current_page_posts = []
                # 鐢ㄤ簬鍘婚噸鐨勫笘瀛怚D闆嗗悎
                processed_tids = set()

                for link in all_links:
                    try:
                        # 鎻愬彇鏍囬鏂囨湰
                        title = link.get_text(strip=True)
                        # 璺宠繃绾暟瀛楃殑鏍囬锛岃繖浜涘彲鑳芥槸鍥炲鏁版垨鍏朵粬鏁板瓧
                        if title.isdigit():
                            continue
                        # 璺宠繃绌烘爣棰?                        if not title:
                            continue
                        # 璺宠繃闈炲笘瀛愰摼鎺ワ紙纭繚鏄痳ead.php閾炬帴锛?                        href = link.get('href', '')
                        if 'read.php' not in href:
                            continue
                        # 璺宠繃鍖呭惈stid鐨勯摼鎺ワ紙閫氬父鏄澘鍧楅摼鎺ワ級
                        if 'stid=' in href:
                            continue

                        thread_url = href

                        # 鎻愬彇thread_id
                        thread_id_match = re.search(r'tid=(\d+)', thread_url)
                        if not thread_id_match:
                            continue
                        thread_id = thread_id_match.group(1)

                        # 妫€鏌ユ槸鍚﹀凡缁忓鐞嗚繃锛堝幓閲嶏紝閬垮厤鐖彇鐗堝ご鍥哄畾甯栧瓙锛?                        if thread_id in processed_tids:
                            print(f"甯栧瓙 {thread_id} 宸插鐞嗚繃锛岃烦杩?)
                            continue

                        # 妫€鏌ユ槸鍚﹀凡缁忔坊鍔犲埌褰撳墠椤靛笘瀛愬垪琛?                        if any(post['thread_id'] == thread_id for post in current_page_posts):
                            continue

                        # 灏嗗笘瀛怚D娣诲姞鍒板凡澶勭悊闆嗗悎
                        processed_tids.add(thread_id)

                        # 鏋勫缓瀹屾暣鐨勫笘瀛怳RL
                        full_thread_url = self._build_post_url(keyword, thread_url)

                        # 灏濊瘯浠庣埗鍏冪礌涓彁鍙栦綔鑰呫€佸洖澶嶆暟鍜屽彂甯冩椂闂?                        author, replies, post_date_str = self._extract_post_metadata(link)

                        # 纭繚鏍囬涓嶅寘鍚玌RL
                        if 'http' in title:
                            # 灏濊瘯浠庣函鏂囨湰涓彁鍙栨爣棰?                            title = re.sub(r'https?://[^\s]+', '', title).strip()

                        # 妫€鏌ュ笘瀛愭槸鍚﹀湪2020/1/1涔嬪悗
                        is_after_2020 = self._is_after_2020(post_date_str)

                        if is_after_2020:
                            current_page_posts.append({
                                'title': title,
                                'thread_id': thread_id,
                                'url': full_thread_url,
                                'author': author,
                                'replies': replies,
                                'post_date': post_date_str
                            })
                            collected_tids.append(thread_id)
                            # 闄愬埗collected_tids鍒楄〃闀垮害锛屽彧淇濈暀鏈€杩?00涓紝閬垮厤鍐呭瓨绱Н
                            if len(collected_tids) > 100:
                                collected_tids = collected_tids[-100:]
                            found_posts += 1
                            print(f"鎵惧埌甯栧瓙: {title} (ID: {thread_id})")

                            # 閲嶇疆杩炵画閬囧埌2020骞翠箣鍓嶅笘瀛愮殑璁℃暟
                            consecutive_old_posts = 0

                            if found_posts >= self.max_posts_per_keyword:
                                break
                        else:
                            print(f"甯栧瓙 {thread_id} 鍙戝竷鏃堕棿鍦?020/1/1涔嬪墠锛岃烦杩?)
                            consecutive_old_posts += 1
                            print(f"杩炵画閬囧埌 {consecutive_old_posts} 涓?020骞翠箣鍓嶇殑甯栧瓙")

                            # 杩炵画閬囧埌5娆?020骞翠箣鍓嶇殑甯栧瓙锛屽垏鎹㈠叧閿瘝
                            if consecutive_old_posts >= max_consecutive_old_posts:
                                print(f"杩炵画閬囧埌 {max_consecutive_old_posts} 涓?020骞翠箣鍓嶇殑甯栧瓙锛屽垏鎹㈠叧閿瘝")
                                return collected_tids
                    except Exception as e:
                        print(f"澶勭悊甯栧瓙閾炬帴鏃跺嚭閿? {e}")
                        continue

                # 鏄惧紡娓呯悊soup瀵硅薄
                del soup
                import gc
                gc.collect()

                # 濡傛灉娌℃湁鎵惧埌鏂板笘瀛愶紝澧炲姞杩炵画绌洪〉闈㈣鏁?                if not current_page_posts:
                    consecutive_empty_pages += 1
                    print(f"杩炵画绌洪〉闈㈡暟: {consecutive_empty_pages}/{max_consecutive_empty_pages}")
                    if consecutive_empty_pages >= max_consecutive_empty_pages:
                        print("杩炵画澶氫釜椤甸潰娌℃湁鎵惧埌鏂板笘瀛愶紝鍋滄缈婚〉")
                        break
                else:
                    consecutive_empty_pages = 0
                    print(f"褰撳墠椤垫壘鍒?{len(current_page_posts)} 涓笘瀛愶紝寮€濮嬪鐞?..")

                    # 绔嬪嵆澶勭悊褰撳墠椤电殑甯栧瓙
                    for i, post in enumerate(current_page_posts, 1):
                        print(f"澶勭悊绗?{i} 涓笘瀛? {post['title']}")
                        if post['thread_id']:
                            try:
                                # 妫€鏌ユ槸鍚︿负澧為噺鐖彇
                                is_incremental = post['thread_id'] in recent_tids
                                if is_incremental:
                                    print(f"甯栧瓙 {post['thread_id']} 鍦ㄦ渶杩憈id鍒楄〃涓紝鎵ц澧為噺鐖彇")
                                else:
                                    print(f"甯栧瓙 {post['thread_id']} 涓嶅湪鏈€杩憈id鍒楄〃涓紝鎵ц鍏ㄩ噺鐖彇")

                                post_detail = await self.get_post_detail(context, post)

                                if post_detail:
                                    context_item = {
                                        'thread_id': post['thread_id'],
                                        'title': post['title'],
                                        'author': post['author'],
                                        'replies': post['replies'],
                                        'post_date': post.get('post_date', '鏈煡'),
                                        'url': post['url'],
                                        'keyword': keyword
                                    }

                                    main_post_item = {
                                        'thread_id': post['thread_id'],
                                        'author': post_detail.get('author', '鏈煡'),
                                        'content': post_detail.get('content', ''),
                                        'type': 'main',
                                        'keyword': keyword,
                                        'post_date': post.get('post_date', '鏈煡')
                                    }

                                    # 鑾峰彇鏃堕棿鎴筹紝濡傛灉post_date涓虹┖鎴?鏈煡'鍒欎娇鐢ㄥ綋鍓嶆椂闂?                                    post_date = post.get('post_date', '鏈煡')
                                    timestamp = post_date if post_date and post_date != '鏈煡' else datetime.now().isoformat()

                                    # 鍙戦€佸埌Kafka
                                    kafka_context_data = {
                                        "platform": "nga",
                                        "type": "post",
                                        "raw_id": post['thread_id'],
                                        "author": post['author'],
                                        "title": post['title'],
                                        "content": post_detail.get('content', ''),
                                        "publish_time": post.get('post_date', ''),
                                        "keyword": keyword,
                                        "view_count": post.get('view_count', 0),
                                        "like_count": post_detail.get('like_count', 0),
                                        "comment_count": post.get('replies', 0),
                                        "coin_count": 0,
                                        "favorite_count": 0,
                                        "share_count": 0,
                                        "danmaku_count": 0,
                                        "is_hot_reply": False,
                                        "author_fans": 0,
                                        "author_level": post_detail.get('author_level', 0),
                                        "author_post_count": post_detail.get('author_post_count', 0),
                                        "has_image": post_detail.get('has_image', False),
                                        "has_video": post_detail.get('has_video', False),
                                        "board_name": post.get('board_name', '')
                                    }
                                    self._send_to_kafka(kafka_context_data, self.kafka_topic)

                                    # 淇濆瓨鍒版枃浠讹紙浣跨敤楂樻晥鐨凧SON杩藉姞鏂瑰紡锛?                                    context_file = os.path.join(context_dir, f'{keyword}.json')
                                    try:
                                        # 妫€鏌ユ枃浠舵槸鍚﹀瓨鍦?                                        file_exists = os.path.exists(context_file)

                                        if not file_exists:
                                            # 鏂囦欢涓嶅瓨鍦紝鍒涘缓骞跺啓鍏ュ紑澶?                                            with open(context_file, 'w', encoding='utf-8') as f:
                                                f.write('\n')
                                            is_first_item = True
                                        else:
                                            # 鏂囦欢瀛樺湪锛屾鏌ユ槸鍚︿负绌?                                            with open(context_file, 'r', encoding='utf-8') as f:
                                                content = f.read().strip()
                                            is_first_item = content == '['

                                        # 浣跨敤杩藉姞妯″紡鍐欏叆鏁版嵁
                                        with open(context_file, 'a', encoding='utf-8') as f:
                                            if not is_first_item:
                                                f.write(',\n')
                                            json.dump(kafka_context_data, f, ensure_ascii=False, indent=2)
                                    except Exception as e:
                                        print(f"淇濆瓨甯栧瓙鍩烘湰淇℃伅鏃跺嚭閿? {e}")

                                    comment_file = os.path.join(comment_dir, f'{keyword}.json')
                                    try:
                                        # 妫€鏌ユ枃浠舵槸鍚﹀瓨鍦?                                        file_exists = os.path.exists(comment_file)

                                        if not file_exists:
                                            # 鏂囦欢涓嶅瓨鍦紝鍒涘缓骞跺啓鍏ュ紑澶?                                            with open(comment_file, 'w', encoding='utf-8') as f:
                                                f.write('\n')
                                            is_first_item = True
                                        else:
                                            # 鏂囦欢瀛樺湪锛屾鏌ユ槸鍚︿负绌?                                            with open(comment_file, 'r', encoding='utf-8') as f:
                                                content = f.read().strip()
                                            is_first_item = content == '['

                                        # 浣跨敤杩藉姞妯″紡鍐欏叆涓诲笘鍐呭
                                        with open(comment_file, 'a', encoding='utf-8') as f:
                                            if not is_first_item:
                                                f.write(',\n')
                                            json.dump(main_post_item, f, ensure_ascii=False, indent=2)
                                    except Exception as e:
                                        print(f"淇濆瓨甯栧瓙璇︾粏淇℃伅鏃跺嚭閿? {e}")

                                    replies = post_detail.get('replies', [])
                                    for reply in replies:
                                        reply_item = {
                                            'thread_id': post['thread_id'],
                                            'author': reply.get('author', '鏈煡'),
                                            'content': reply.get('content', ''),
                                            'type': 'reply',
                                            'keyword': keyword,
                                            'post_date': reply.get('post_date', '')
                                        }

                                        # 鑾峰彇鍥炲鏃堕棿鎴?                                        reply_date = reply.get('post_date', '')
                                        reply_timestamp = reply_date if reply_date and reply_date != '' else datetime.now().isoformat()

                                        # 鍙戦€佸洖澶嶅埌Kafka
                                        kafka_reply_data = {
                                            "platform": "nga",
                                            "type": "reply",
                                            "raw_id": post['thread_id'],
                                            "author": reply.get('author', '鏈煡'),
                                            "title": post['title'],
                                            "content": reply.get('content', ''),
                                            "publish_time": reply.get('post_date', ''),
                                            "keyword": keyword,
                                            "view_count": 0,
                                            "like_count": 0,
                                            "comment_count": 0,
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
                                            "board_name": post.get('board_name', '')
                                        }
                                        self._send_to_kafka(kafka_reply_data, self.kafka_topic)

                                        # 淇濆瓨鍥炲鍒版枃浠?                                        try:
                                            # 妫€鏌ユ枃浠舵槸鍚﹀瓨鍦?                                            file_exists = os.path.exists(comment_file)

                                            if not file_exists:
                                                # 鏂囦欢涓嶅瓨鍦紝鍒涘缓骞跺啓鍏ュ紑澶?                                                with open(comment_file, 'w', encoding='utf-8') as f:
                                                    f.write('\n')
                                                is_first_item = True
                                            else:
                                                # 鏂囦欢瀛樺湪锛屾鏌ユ槸鍚︿负绌?                                                with open(comment_file, 'r', encoding='utf-8') as f:
                                                    content = f.read().strip()
                                                is_first_item = content == '['

                                            # 浣跨敤杩藉姞妯″紡鍐欏叆鍥炲
                                            with open(comment_file, 'a', encoding='utf-8') as f:
                                                if not is_first_item:
                                                    f.write(',\n')
                                                json.dump(kafka_reply_data, f, ensure_ascii=False, indent=2)
                                        except Exception as e:
                                            print(f"淇濆瓨鍥炲鏃跺嚭閿? {e}")

                                print(f"澶勭悊绗?{i} 涓笘瀛愬畬鎴?)
                            except Exception as e:
                                print(f"澶勭悊绗?{i} 涓笘瀛愭椂鍑洪敊: {e}")
                                continue

                    # 娓呯┖褰撳墠椤电殑甯栧瓙鍒楄〃锛岄噴鏀惧唴瀛?                    current_page_posts.clear()
                    print(f"宸叉竻绌哄綋鍓嶉〉甯栧瓙鍒楄〃锛岄噴鏀惧唴瀛?)

                # 淇濆瓨鐘舵€?                self.current_status['current_page'] = page_num
                self.current_status['posts_collected'] = found_posts
                self.save_status()

                # 妫€鏌ユ槸鍚﹁揪鍒版渶澶у笘瀛愭暟
                if found_posts >= self.max_posts_per_keyword:
                    print(f"宸茶揪鍒版渶澶у笘瀛愭暟 {self.max_posts_per_keyword}锛屽仠姝㈢埇鍙?)
                    break

                # 缈婚〉
                page_num += 1
                # 娣诲姞寤惰繜锛?-4绉掞級
                await self._random_delay(2, 4)

            print(f"鐖彇瀹屾垚锛屽叡鏀堕泦 {found_posts} 涓笘瀛?)

            # 鍏抽棴鎵€鏈塉SON鏂囦欢锛屾坊鍔犵粨鏉熺
            self._close_json_files(context_dir, comment_dir, keyword)

            return collected_tids
        except Exception as e:
            print(f"鐖彇鏉垮潡鏃跺嚭閿? {e}")
            return []

    def _build_forum_url(self, keyword, fid, page_num):
        """鏋勫缓鏉垮潡URL"""
        if keyword == "鏄庢棩鏂硅垷":
            return f'https://bbs.nga.cn/thread.php?fid={fid}&page={page_num}'
        else:
            if fid > 0:
                return f'{self.base_url}/thread.php?fid={fid}&page={page_num}'
            else:
                return f'{self.base_url}/thread.php?stid={abs(fid)}&page={page_num}'

    def _build_post_url(self, keyword, thread_url):
        """鏋勫缓瀹屾暣鐨勫笘瀛怳RL"""
        if keyword == "鏄庢棩鏂硅垷":
            if thread_url.startswith('/'):
                return f'https://bbs.nga.cn{thread_url}'
            elif not thread_url.startswith('http'):
                return f'https://bbs.nga.cn/{thread_url}'
            else:
                return thread_url
        else:
            if thread_url.startswith('/'):
                return f'{self.base_url}{thread_url}'
            elif not thread_url.startswith('http'):
                return f'{self.base_url}/{thread_url}'
            else:
                return thread_url

    def _extract_post_metadata(self, link):
        """浠庨摼鎺ョ埗鍏冪礌涓彁鍙栦綔鑰呫€佸洖澶嶆暟鍜屽彂甯冩椂闂?""
        author = '鏈煡'
        replies = '0'
        post_date_str = ''

        parent = link.parent
        while parent:
            author_elem = parent.select_one('.author') or parent.select_one('.username') or parent.select_one('.user')
            if author_elem:
                author = author_elem.get_text(strip=True)

            replies_elem = parent.select_one('.replies') or parent.select_one('.reply-count')
            if replies_elem:
                replies_text = replies_elem.get_text(strip=True)
                replies_match = re.search(r'(\d+)', replies_text)
                if replies_match:
                    replies = replies_match.group(1)

            date_elem = parent.select_one('.postdate') or parent.select_one('.date') or parent.select_one('.time')
            if date_elem:
                post_date_str = date_elem.get_text(strip=True)

            if parent.name == 'tr' or 'post' in str(parent.get('class', [])):
                break
            parent = parent.parent

        return author, replies, post_date_str

    def _is_after_2020(self, post_date_str):
        """妫€鏌ュ笘瀛愭棩鏈熸槸鍚﹀湪2020/1/1涔嬪悗"""
        if not post_date_str:
            return True

        try:
            # 灏濊瘯瑙ｆ瀽鍚勭鏃ユ湡鏍煎紡
            date_patterns = [
                r'(\d{4})-(\d{1,2})-(\d{1,2})',
                r'(\d{4})/(\d{1,2})/(\d{1,2})',
                r'(\d{4})骞?\d{1,2})鏈?\d{1,2})鏃?,
            ]

            for pattern in date_patterns:
                match = re.search(pattern, post_date_str)
                if match:
                    year = int(match.group(1))
                    month = int(match.group(2))
                    day = int(match.group(3))

                    if year > 2020:
                        return True
                    elif year == 2020:
                        if month > 1:
                            return True
                        elif month == 1 and day >= 1:
                            return True
                    return False

            # 濡傛灉鏃犳硶瑙ｆ瀽鏃ユ湡锛岄粯璁よ繑鍥濼rue
            return True
        except Exception as e:
            print(f"瑙ｆ瀽鏃ユ湡鏃跺嚭閿? {e}, 鏃ユ湡瀛楃涓? {post_date_str}")
            return True

    def _create_output_directories(self, crawl_time):
        """鍒涘缓杈撳嚭鐩綍"""
        context_dir = os.path.join(self.output_dir, crawl_time, 'context')
        comment_dir = os.path.join(self.output_dir, crawl_time, 'comment')
        self._ensure_directory(context_dir)
        self._ensure_directory(comment_dir)
        return context_dir, comment_dir

    async def get_post_detail(self, context, post):
        """鑾峰彇甯栧瓙璇︽儏"""
        thread_id = post.get('thread_id')
        if not thread_id:
            return None

        print(f"鑾峰彇甯栧瓙璇︽儏: {post.get('title', '鏈煡鏍囬')} (ID: {thread_id})")

        page = None
        try:
            page = await context.new_page()

            replies = []
            main_content = ""
            page_num = 1
            max_pages = 100

            while page_num <= max_pages:
                post_url = self._build_post_detail_url(post, thread_id, page_num)
                print(f"璁块棶甯栧瓙绗?{page_num} 椤? {post_url}")

                await page.goto(post_url)
                await page.wait_for_load_state('networkidle')

                content = await page.content()

                if '姝ゅ笘瀛愯閿佸畾' in content:
                    print(f"甯栧瓙 {thread_id} 琚攣瀹氾紝璺宠繃")
                    await page.close()
                    return self._create_post_data(thread_id, post, f"甯栧瓙琚攣瀹氾紙ID: {thread_id}锛?, [])

                soup = BeautifulSoup(content, 'html.parser')

                # 绗竴椤垫彁鍙栦富璐村唴瀹?                if page_num == 1:
                    main_content = self._extract_main_content(soup, thread_id)

                # 鎻愬彇鍥炲
                print(f"寮€濮嬫彁鍙栫 {page_num} 椤靛洖澶?..")

                # 鎻愬彇鐑偣鍥炲锛堝彧鍦ㄧ涓€椤碉級
                if page_num == 1:
                    replies.extend(self._extract_hot_replies(soup))

                # 鎻愬彇鏅€氬洖澶?                replies.extend(self._extract_normal_replies(soup, page_num))

                # 妫€鏌ユ槸鍚︽湁涓嬩竴椤?                has_next_page = self._has_next_page(soup)

                if not has_next_page:
                    print("娌℃湁鏇村鍥炲椤?)
                    break

                page_num += 1
                # 娣诲姞寤惰繜
                await self._random_delay(1, 2)

            print(f"鎬诲叡鎵惧埌 {len(replies)} 涓洖澶?)

            return self._create_post_data(thread_id, post, main_content, replies)
        except Exception as e:
            print(f"鑾峰彇甯栧瓙璇︽儏鏃跺嚭閿? {e}")
            # 濡傛灉鑾峰彇澶辫触锛岃繑鍥炲熀鏈俊鎭?            return self._create_post_data(thread_id, post, f"甯栧瓙鍐呭锛圛D: {thread_id}锛?, [])
        finally:
            # 纭繚椤甸潰琚叧闂?            if page:
                await page.close()
                print(f"宸插叧闂笘瀛愯鎯呴〉: {thread_id}")

    def _build_post_detail_url(self, post, thread_id, page_num):
        """鏋勫缓甯栧瓙璇︽儏URL"""
        if 'bbs.nga.cn' in post.get('url', ''):
            return f'https://bbs.nga.cn/read.php?tid={thread_id}&page={page_num}'
        else:
            return f'{self.base_url}/read.php?tid={thread_id}&page={page_num}'

    def _extract_main_content(self, soup, thread_id):
        """鎻愬彇涓昏创鍐呭"""
        content_elem = soup.select_one('.t_f')
        if not content_elem:
            content_elem = soup.select_one('.postcontent')

        if content_elem:
            main_content = content_elem.get_text(strip=True)
            print(f"鎻愬彇鍒颁富璐村唴瀹癸紝闀垮害: {len(main_content)}")
        else:
            main_content = f"甯栧瓙鍐呭锛圛D: {thread_id}锛?
            print("鏈壘鍒颁富璐村唴瀹癸紝浣跨敤鍗犱綅绗?)

        return main_content

    def _extract_hot_replies(self, soup):
        """鎻愬彇鐑偣鍥炲"""
        replies = []
        comment_elems = soup.find_all('div', class_='comment_c')
        print(f"鏂瑰紡1 - 鎵惧埌 {len(comment_elems)} 涓儹鐐瑰洖澶嶅厓绱?)

        for comment_elem in comment_elems:
            try:
                author = '鏈煡'
                author_elem = comment_elem.find('a', class_='userlink')
                if author_elem:
                    author = author_elem.get_text(strip=True)

                reply_content = ''
                content_elem = comment_elem.find(class_='ubbcode')
                if content_elem:
                    reply_content = content_elem.get_text(strip=True)
                    # 绉婚櫎鏈€鍚庣殑"鈥︹€?[鍘熷笘]"
                    reply_content = reply_content.replace('鈥︹€?[鍘熷笘]', '').strip()

                # 鎻愬彇鍥炲鏃堕棿
                reply_time = ''
                time_elem = comment_elem.find(class_='postdate')
                if time_elem:
                    reply_time = time_elem.get_text(strip=True)

                if reply_content:
                    replies.append({
                        'author': author,
                        'content': reply_content,
                        'post_date': reply_time
                    })
            except Exception as e:
                print(f"鎻愬彇鐑偣鍥炲鏃跺嚭閿? {e}")
                continue

        return replies

    def _extract_normal_replies(self, soup, page_num):
        """鎻愬彇鏅€氬洖澶?""
        replies = []
        post_elems = soup.find_all('tr', class_='postrow')
        print(f"鏂瑰紡2 - 鎵惧埌 {len(post_elems)} 涓櫘閫氬洖澶嶅厓绱?)

        for i, post_elem in enumerate(post_elems, 1):
            # 璺宠繃涓昏创锛堥€氬父鏄涓€涓級
            if page_num == 1 and i == 1:
                continue

            try:
                author = '鏈煡'
                author_elem = post_elem.find('a', class_='userlink')
                if author_elem:
                    author = author_elem.get_text(strip=True)

                reply_content = ''
                content_elem = post_elem.find(class_='postcontent')
                if not content_elem:
                    content_elem = post_elem.find(class_='ubbcode')

                if content_elem:
                    reply_content = content_elem.get_text(strip=True)

                # 鎻愬彇鍥炲鏃堕棿
                reply_time = ''
                time_elem = post_elem.find(class_='postdate')
                if time_elem:
                    reply_time = time_elem.get_text(strip=True)

                if reply_content:
                    replies.append({
                        'author': author,
                        'content': reply_content,
                        'post_date': reply_time
                    })
            except Exception as e:
                print(f"鎻愬彇鏅€氬洖澶嶆椂鍑洪敊: {e}")
                continue

        return replies

    def _has_next_page(self, soup):
        """妫€鏌ユ槸鍚︽湁涓嬩竴椤?""
        # 鏂瑰紡1: 鏌ユ壘鏂囨湰涓?涓嬩竴椤?鐨勯摼鎺?        next_page = soup.find('a', text='涓嬩竴椤?)
        if next_page:
            print(f"鎵惧埌涓嬩竴椤甸摼鎺ワ紙鏂瑰紡1锛? {next_page.get('href', '')}")
            return True

        # 鏂瑰紡2: 鏌ユ壘鍖呭惈"page="鐨勯摼鎺?        page_links = soup.find_all('a', href=re.compile(r'page=\d+'))
        for link in page_links:
            link_text = link.get_text(strip=True)
            if '涓嬩竴椤? in link_text or '>' in link_text:
                print(f"鎵惧埌涓嬩竴椤甸摼鎺ワ紙鏂瑰紡2锛? {link.get('href', '')}")
                return True

        # 鏂瑰紡3: 鏌ユ壘鍒嗛〉鍖哄煙
        pagination = soup.find('div', class_='pages')
        if pagination:
            page_links = pagination.find_all('a')
            for link in page_links:
                link_text = link.get_text(strip=True)
                if '涓嬩竴椤? in link_text or '>' in link_text:
                    print(f"鎵惧埌涓嬩竴椤甸摼鎺ワ紙鏂瑰紡3锛? {link.get('href', '')}")
                    return True

        return False

    def _create_post_data(self, thread_id, post, content, replies):
        """鍒涘缓甯栧瓙鏁版嵁"""
        return {
            'thread_id': thread_id,
            'title': post['title'],
            'author': post['author'],
            'content': content,
            'replies': replies,
            'post_time': post.get('post_date', ''),
            'keyword': post.get('keyword', ''),
            'view_count': post.get('view_count', 0),
            'like_count': post.get('like_count', 0),
            'floor': 1,
            'quote': '',
            'is_hot_reply': False,
            'author_level': post.get('author_level', 0),
            'author_post_count': post.get('author_post_count', 0),
            'board_name': post.get('board_name', ''),
            'has_image': post.get('has_image', False),
            'has_video': post.get('has_video', False)
        }

    async def _random_delay(self, min_delay, max_delay):
        """闅忔満寤惰繜锛岄伩鍏嶈鍙嶇埇铏?""
        delay = random.uniform(min_delay, max_delay)
        await asyncio.sleep(delay)

    def load_recent_tids(self, keyword):
        """鍔犺浇鏈€杩戠殑tid鍒楄〃锛堟寜鍏抽敭璇嶏級"""
        tid_file = os.path.join(self.output_dir, f'recent_tids_{keyword}.json')
        if os.path.exists(tid_file):
            try:
                with open(tid_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('recent_tids', [])
            except Exception as e:
                print(f"鍔犺浇tid鍒楄〃鏃跺嚭閿? {e}")
        return []

    def _close_json_files(self, context_dir, comment_dir, keyword):
        """鍏抽棴鎵€鏈塉SON鏂囦欢锛屾坊鍔犵粨鏉熺"""
        # 鍏抽棴context鏂囦欢
        context_file = os.path.join(context_dir, f'{keyword}.json')
        if os.path.exists(context_file):
            try:
                with open(context_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                if content and not content.endswith(']'):
                    with open(context_file, 'a', encoding='utf-8') as f:
                        f.write('\n]')
                print(f"宸插叧闂璫ontext鏂囦欢: {context_file}")
            except Exception as e:
                print(f"鍏抽棴context鏂囦欢鏃跺嚭閿? {e}")

        # 鍏抽棴comment鏂囦欢
        comment_file = os.path.join(comment_dir, f'{keyword}.json')
        if os.path.exists(comment_file):
            try:
                with open(comment_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                if content and not content.endswith(']'):
                    with open(comment_file, 'a', encoding='utf-8') as f:
                        f.write('\n]')
                print(f"宸插叧闂璫omment鏂囦欢: {comment_file}")
            except Exception as e:
                print(f"鍏抽棴comment鏂囦欢鏃跺嚭閿? {e}")

    def save_recent_tids(self, keyword, tids):
        """淇濆瓨鏈€杩戠殑tid鍒楄〃锛屾渶澶氫繚瀛?0涓紙鎸夊叧閿瘝锛?""
        recent_tids = tids[-50:]
        tid_file = os.path.join(self.output_dir, f'recent_tids_{keyword}.json')
        try:
            with open(tid_file, 'w', encoding='utf-8') as f:
                json.dump({'recent_tids': recent_tids}, f, ensure_ascii=False, indent=2)
            print(f"宸蹭繚瀛?{len(recent_tids)} 涓渶杩戠殑tid")
        except Exception as e:
            print(f"淇濆瓨tid鍒楄〃鏃跺嚭閿? {e}")

    def save_last_crawl_time(self):
        """淇濆瓨涓婃鐖彇鏃堕棿"""
        try:
            last_crawl_time = datetime.now().isoformat()
            with open(self.last_crawl_time_file, 'w', encoding='utf-8') as f:
                json.dump({'last_crawl_time': last_crawl_time}, f, ensure_ascii=False, indent=2)
            print(f"宸蹭繚瀛樹笂娆＄埇鍙栨椂闂? {last_crawl_time}")
        except Exception as e:
            print(f"淇濆瓨涓婃鐖彇鏃堕棿鏃跺嚭閿? {e}")

    def save_status(self):
        """淇濆瓨鐖彇鐘舵€?""
        try:
            with open(self.status_file, 'w', encoding='utf-8') as f:
                json.dump(self.current_status, f, ensure_ascii=False, indent=2)
            print(f"宸蹭繚瀛樼埇鍙栫姸鎬? {self.current_status}")
        except Exception as e:
            print(f"淇濆瓨鐘舵€佹椂鍑洪敊: {e}")

    def load_status(self):
        """鍔犺浇鐖彇鐘舵€?""
        if os.path.exists(self.status_file):
            try:
                with open(self.status_file, 'r', encoding='utf-8') as f:
                    self.current_status = json.load(f)
                print(f"宸插姞杞界埇鍙栫姸鎬? {self.current_status}")
                return True
            except Exception as e:
                print(f"鍔犺浇鐘舵€佹椂鍑洪敊: {e}")
        return False


def load_config():
    """鍔犺浇閰嶇疆鏂囦欢"""
    config_path = 'config.json'
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        return {
            "cookies": {},
            "keywords": ["榄斿吔涓栫晫"]
        }


async def main():
    try:
        config = load_config()
        crawler = NGACrawlerPlaywright(config)
        await crawler.run()
    except Exception as e:
        print(f"杩愯鐖櫕鏃跺嚭閿? {e}")


if __name__ == "__main__":
    asyncio.run(main())