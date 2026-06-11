import asyncio
import json
import os
import random
import re
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from kafka import KafkaProducer

class NGACrawlerPlaywright:
    """NGA论坛爬虫"""
    
    def __init__(self, config):
        """初始化爬虫"""
        self.config = config
        self.cookies = config.get('cookies', {})
        self.keywords = config.get('keywords', [])
        self.base_url = 'https://ngabbs.com'
        self.output_dir = '/data/NGA'
        self.max_posts_per_keyword = 10000
        self.status_file = os.path.join(self.output_dir, 'crawler_status.json')
        self.last_crawl_time_file = os.path.join(self.output_dir, 'last_crawl_time.json')
        
        # 关键词到FID的映射
        self.NGA_GAME_FID = {
            "手机游戏": 863,                    
            "王者荣耀": 516, 
            "和平精英": 599, 
            "原神": 650, 
            "崩坏星穹铁道": 818, 
            "绝区零": 853, 
            "明日方舟": -34587507, 
            "崩坏三": 549, 
            "天涯明月刀": -23052020, 
            "无限暖暖": 510373, 
            "英雄联盟手游": 681, 
            "金铲铲之战": 510461, 
            "明日方舟终末地": 846, 
            "三角洲行动": 510489, 
            "火影忍者手游": -19317848, 
            "燕云十六声": 510527, 
            "逆水寒手游": 510407, 
            "永劫无间手游": -39735775, 
            "光遇": -22495125, 
            "第五人格": 607, 
            "阴阳师": 538 
        }
        
        # 初始化爬取状态
        self.current_status = {
            'current_keyword_index': 0,
            'current_page': 1,
            'posts_collected': 0,
            'mode': 'full',  # 'full' 或 'incremental'
            'last_crawl_time': None
        }
        
        # 创建输出目录
        self._ensure_directory(self.output_dir)
        
        # Kafka配置
        kafka_config = config.get('kafka', {})
        self.kafka_enabled = kafka_config.get('enabled', False)
        self.kafka_bootstrap_servers = kafka_config.get('bootstrap_servers', 'localhost:9092')
        self.kafka_topic = kafka_config.get('topic', 'nga_crawler')
        self.kafka_producer = None
    
    def _ensure_directory(self, directory):
        """确保目录存在"""
        if not os.path.exists(directory):
            os.makedirs(directory)
    
    def _init_kafka_producer(self):
        """初始化Kafka生产者"""
        if self.kafka_enabled:
            try:
                self.kafka_producer = KafkaProducer(
                    bootstrap_servers=self.kafka_bootstrap_servers,
                    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                    api_version=(0, 10, 1),
                    retries=3,
                    batch_size=16384,
                    linger_ms=10,
                    buffer_memory=33554432
                )
                print(f"Kafka生产者初始化成功: {self.kafka_bootstrap_servers}")
            except Exception as e:
                print(f"Kafka生产者初始化失败: {e}")
                self.kafka_enabled = False
    
    def _send_to_kafka(self, data):
        """发送数据到Kafka"""
        if self.kafka_enabled and self.kafka_producer:
            try:
                self.kafka_producer.send(self.kafka_topic, value=data)
                # 同步发送，确保消息立即发送
                self.kafka_producer.flush()
            except Exception as e:
                print(f"发送数据到Kafka失败: {e}")
    
    async def run(self):
        """运行爬虫"""
        try:
            start_time = datetime.now()
            print(f"爬虫开始运行，时间: {start_time}")
            print(f"关键词数量: {len(self.keywords)}")
            
            # 加载爬取状态
            status_loaded = self.load_status()
            
            async with async_playwright() as p:
                print("正在启动浏览器...")
                browser = await self._launch_browser(p)
                context = await browser.new_context()
                
                if self.cookies:
                    await self._login(context)
                
                # 初始化Kafka生产者
                self._init_kafka_producer()
                
                # 从保存的位置继续爬取
                start_index = self.current_status.get('current_keyword_index', 0)
                
                for i, keyword in enumerate(self.keywords[start_index:], start=start_index):
                    print(f"\n开始处理关键词: {keyword}")
                    # 更新当前关键词索引
                    self.current_status['current_keyword_index'] = i
                    self.current_status['current_page'] = 1
                    self.current_status['posts_collected'] = 0
                    self.current_status['last_crawl_time'] = start_time.isoformat()
                    self.save_status()
                    
                    # 加载对应关键词的tid列表
                    recent_tids = self.load_recent_tids(keyword)
                    print(f"已加载 {len(recent_tids)} 个最近的tid")
                    
                    # 初始化爬取模式
                    if not status_loaded:
                        # 首次运行，检查是否有最近的tid列表
                        if recent_tids:
                            self.current_status['mode'] = 'incremental'
                            print("检测到最近的tid列表，使用增量爬取模式")
                        else:
                            self.current_status['mode'] = 'full'
                            print("未检测到最近的tid列表，使用全量爬取模式")
                    else:
                        print(f"恢复爬取模式: {self.current_status['mode']}")
                    
                    tids = await self.crawl_forum(context, keyword, start_time, recent_tids)
                    
                    # 保存对应关键词的tid列表
                    if tids:
                        self.save_recent_tids(keyword, tids)
                    
                    # 保存状态
                    self.save_status()
                    
                    if i < len(self.keywords) - 1:
                        print("切换关键词，添加延迟...")
                        await self._random_delay(10, 15)
                
                # 关闭Kafka生产者
                if self.kafka_producer:
                    try:
                        self.kafka_producer.close()
                        print("已关闭Kafka生产者")
                    except Exception as e:
                        print(f"关闭Kafka生产者时出错: {e}")
                
                await browser.close()
                
                # 保存最后爬取时间
                self.save_last_crawl_time()
                
                # 爬取完成，清除状态
                if os.path.exists(self.status_file):
                    os.remove(self.status_file)
                    print("爬取完成，已清除状态文件")
                
                end_time = datetime.now()
                print(f"\n爬虫完成，总运行时间: {end_time - start_time}")
        except Exception as e:
            # 出错时保存状态
            self.save_status()
            print(f"运行爬虫时出错: {e}")
    
    async def _launch_browser(self, playwright):
        """启动浏览器，优先使用系统Chrome"""
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
            print("使用系统Chrome浏览器成功")
        except Exception as e:
            print(f"使用系统Chrome失败: {e}，尝试使用Playwright默认浏览器")
            browser = await playwright.chromium.launch(headless=True)
        return browser
    
    async def _login(self, context):
        """登录NGA论坛"""
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
            print("登录中...")
            # 测试登录状态
            test_page = await context.new_page()
            await test_page.goto(f'{self.base_url}/')
            await test_page.wait_for_load_state('networkidle')
            test_content = await test_page.content()
            await test_page.close()
            
            if 'MaIO233' in test_content:
                print("登录成功")
            else:
                print("登录失败，尝试继续爬取")
    
    async def crawl_forum(self, context, keyword, start_time, recent_tids):
        """直接爬取对应板块的帖子（支持增量爬取）"""
        try:
            # 获取对应的FID
            fid = self.NGA_GAME_FID.get(keyword)
            if not fid:
                print(f"未找到关键词 '{keyword}' 对应的FID，跳过")
                return []
            
            posts = []
            found_posts = self.current_status.get('posts_collected', 0)
            page_num = self.current_status.get('current_page', 1)
            collected_tids = []
            
            while found_posts < self.max_posts_per_keyword:
                # 构建板块URL
                forum_url = self._build_forum_url(keyword, fid, page_num)
                
                print(f"访问板块: {keyword} (FID: {fid})，第 {page_num} 页")
                print(f"访问URL: {forum_url}")
                
                page = await context.new_page()
                print("正在访问板块页面...")
                await page.goto(forum_url)
                print("等待页面加载完成...")
                await page.wait_for_load_state('networkidle')
                print("页面加载完成")
                
                content = await page.content()
                await page.close()
                
                soup = BeautifulSoup(content, 'html.parser')
                
                # 找到所有帖子链接
                all_links = soup.find_all('a', href=re.compile(r'tid=\d+'))
                print(f"找到 {len(all_links)} 个包含tid的链接")
                
                # 如果没有找到链接，说明已经到最后一页
                if not all_links:
                    print("未找到更多帖子，停止翻页")
                    break
                
                for link in all_links:
                    try:
                        # 提取标题文本
                        title = link.get_text(strip=True)
                        # 跳过纯数字的标题，这些可能是回复数或其他数字
                        if title.isdigit():
                            continue
                        # 跳过空标题
                        if not title:
                            continue
                        # 跳过非帖子链接（确保是read.php链接）
                        href = link.get('href', '')
                        if 'read.php' not in href:
                            continue
                        # 跳过包含stid的链接（通常是板块链接）
                        if 'stid=' in href:
                            continue
                        
                        thread_url = href
                        
                        # 提取thread_id
                        thread_id_match = re.search(r'tid=(\d+)', thread_url)
                        if not thread_id_match:
                            continue
                        thread_id = thread_id_match.group(1)
                        
                        # 检查是否已经添加过
                        if any(post['thread_id'] == thread_id for post in posts):
                            continue
                        
                        # 构建完整的帖子URL
                        full_thread_url = self._build_post_url(keyword, thread_url)
                        
                        # 尝试从父元素中提取作者、回复数和发布时间
                        author, replies, post_date_str = self._extract_post_metadata(link)
                        
                        # 确保标题不包含URL
                        if 'http' in title:
                            # 尝试从纯文本中提取标题
                            title = re.sub(r'https?://[^\s]+', '', title).strip()
                        
                        # 检查帖子是否在2020/1/1之后
                        is_within_range = self._is_within_range(post_date_str)
                        
                        if is_within_range:
                            posts.append({
                                'title': title,
                                'thread_id': thread_id,
                                'url': full_thread_url,
                                'author': author,
                                'replies': replies,
                                'post_date': post_date_str
                            })
                            collected_tids.append(thread_id)
                            found_posts += 1
                            print(f"找到帖子: {title} (ID: {thread_id})")
                            
                            # 每处理10个帖子保存一次状态
                            if found_posts % 10 == 0:
                                self.current_status['current_page'] = page_num
                                self.current_status['posts_collected'] = found_posts
                                self.save_status()
                            
                            if found_posts >= self.max_posts_per_keyword:
                                break
                        else:
                            print(f"跳过2020/1/1之前的帖子: {title} (ID: {thread_id})")
                            print("检测到2020/1/1之前的帖子，停止当前关键词的爬取")
                            return collected_tids
                    except Exception as e:
                        print(f"处理帖子链接时出错: {e}")
                        continue
                
                # 翻页
                page_num += 1
                # 更新状态
                self.current_status['current_page'] = page_num
                self.current_status['posts_collected'] = found_posts
                self.save_status()
                # 添加延迟（2-4秒）
                await self._random_delay(2, 4)
            
            if not posts:
                print(f"未找到关于 '{keyword}' 的帖子")
                return collected_tids
            
            print(f"总共找到 {len(posts)} 个帖子")
            
            # 创建时间戳文件夹（精度为天）
            crawl_time = datetime.now().strftime('%Y-%m-%d')
            context_dir, comment_dir = self._create_output_directories(crawl_time)
            
            # 使用分批处理，每批处理10个帖子
            batch_size = 10
            total_posts = len(posts)
            
            for batch_start in range(0, total_posts, batch_size):
                batch_end = min(batch_start + batch_size, total_posts)
                batch_posts = posts[batch_start:batch_end]
                
                context_data = []
                comment_data = []
                
                print(f"处理批次 {batch_start//batch_size + 1}/{(total_posts + batch_size - 1)//batch_size}，帖子 {batch_start+1}-{batch_end}")
                
                for i, post in enumerate(batch_posts, batch_start + 1):
                    print(f"处理第 {i} 个帖子: {post['title']}")
                    if post['thread_id']:
                        try:
                            # 检查是否为增量爬取
                            is_incremental = post['thread_id'] in recent_tids
                            if is_incremental:
                                print(f"帖子 {post['thread_id']} 在最近tid列表中，执行增量爬取")
                            else:
                                print(f"帖子 {post['thread_id']} 不在最近tid列表中，执行全量爬取")
                            
                            post_detail = await self.get_post_detail(context, post)
                            
                            if post_detail:
                                context_item = {
                                    'thread_id': post['thread_id'],
                                    'title': post['title'],
                                    'author': post['author'],
                                    'replies': post['replies'],
                                    'post_date': post.get('post_date', '未知'),
                                    'url': post['url']
                                }
                                context_data.append(context_item)
                                
                                main_post_item = {
                                    'thread_id': post['thread_id'],
                                    'author': post_detail.get('author', '未知'),
                                    'content': post_detail.get('content', ''),
                                    'type': 'main'
                                }
                                comment_data.append(main_post_item)
                                
                                replies = post_detail.get('replies', [])
                                for reply in replies:
                                    reply_item = {
                                        'thread_id': post['thread_id'],
                                        'author': reply.get('author', '未知'),
                                        'content': reply.get('content', ''),
                                        'type': 'reply'
                                    }
                                    comment_data.append(reply_item)
                            print(f"处理第 {i} 个帖子完成")
                        except Exception as e:
                            print(f"处理第 {i} 个帖子时出错: {e}")
                            continue
                    
                    await asyncio.sleep(1)
                
                # 保存当前批次的数据
                if context_data:
                    self._save_batch_data(context_dir, comment_dir, keyword, context_data, comment_data, batch_start)
                
                # 清空当前批次的数据，释放内存
                del context_data
                del comment_data
                del batch_posts
                
                # 强制垃圾回收
                import gc
                gc.collect()
            
            # 清空帖子列表，释放内存
            del posts
            import gc
            gc.collect()
            
            return collected_tids
        except Exception as e:
            print(f"爬取板块时出错: {e}")
            return []
    
    def _build_forum_url(self, keyword, fid, page_num):
        """构建板块URL"""
        if keyword == "明日方舟":
            return f'https://bbs.nga.cn/thread.php?fid={fid}&page={page_num}'
        else:
            if fid > 0:
                return f'{self.base_url}/thread.php?fid={fid}&page={page_num}'
            else:
                return f'{self.base_url}/thread.php?stid={abs(fid)}&page={page_num}'
    
    def _build_post_url(self, keyword, thread_url):
        """构建完整的帖子URL"""
        if keyword == "明日方舟":
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
        """从链接父元素中提取作者、回复数和发布时间"""
        author = '未知'
        replies = '0'
        post_date_str = ''
        
        parent = link.parent
        while parent:
            author_elem = parent.select_one('.author') or parent.select_one('.username') or parent.select_one('.user')
            if author_elem:
                author = author_elem.get_text(strip=True)
            
            reply_elem = parent.select_one('.replies') or parent.select_one('.reply_count')
            if reply_elem:
                replies = reply_elem.get_text(strip=True)
            
            postdate_elem = parent.select_one('.postdate') or parent.select_one('.date')
            if postdate_elem:
                post_date_str = postdate_elem.get_text(strip=True)
            
            # 如果已经找到所有信息，就停止
            if author != '未知' and replies != '0' and post_date_str:
                break
            
            parent = parent.parent
        
        return author, replies, post_date_str
    
    def _is_within_range(self, post_date_str):
        """检查帖子是否在上次爬取时间之后"""
        if not post_date_str:
            return True

        try:
            # 获取上次爬取时间
            last_crawl_time = self._get_last_crawl_time()
            if not last_crawl_time:
                # 首次爬取，使用2020/1/1作为起始时间
                cutoff_date = datetime(2020, 1, 1)
            else:
                cutoff_date = last_crawl_time
            
            if '今天' in post_date_str:
                return True
            elif '昨天' in post_date_str:
                return True
            elif '前天' in post_date_str:
                return True
            elif re.match(r'\d{4}-\d{2}-\d{2}', post_date_str):
                post_date = datetime.strptime(post_date_str, '%Y-%m-%d')
                return post_date >= cutoff_date
            elif re.match(r'\d{2}-\d{2}', post_date_str):
                current_year = datetime.now().year
                date_str = f'{current_year}-{post_date_str}'
                post_date = datetime.strptime(date_str, '%Y-%m-%d')
                return post_date >= cutoff_date
            else:
                return True
        except Exception:
            return True
    
    def _create_output_directories(self, crawl_time):
        """创建输出目录"""
        keyword_output_dir = os.path.join(self.output_dir, crawl_time)
        context_dir = os.path.join(keyword_output_dir, 'context')
        comment_dir = os.path.join(keyword_output_dir, 'comment')
        
        for dir_path in [keyword_output_dir, context_dir, comment_dir]:
            self._ensure_directory(dir_path)
        
        return context_dir, comment_dir
    
    def _save_batch_data(self, context_dir, comment_dir, keyword, context_data, comment_data, batch_start):
        """保存批次数据"""
        context_file = os.path.join(context_dir, f'{keyword}.json')
        try:
            if batch_start == 0:
                with open(context_file, 'w', encoding='utf-8') as f:
                    json.dump(context_data, f, ensure_ascii=False, indent=2)
            else:
                with open(context_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                existing_data.extend(context_data)
                with open(context_file, 'w', encoding='utf-8') as f:
                    json.dump(existing_data, f, ensure_ascii=False, indent=2)
            print(f"帖子基本信息已保存到: {context_file}")
        except Exception as e:
            print(f"保存帖子基本信息时出错: {e}")
        
        comment_file = os.path.join(comment_dir, f'{keyword}.json')
        try:
            if batch_start == 0:
                with open(comment_file, 'w', encoding='utf-8') as f:
                    json.dump(comment_data, f, ensure_ascii=False, indent=2)
            else:
                with open(comment_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                existing_data.extend(comment_data)
                with open(comment_file, 'w', encoding='utf-8') as f:
                    json.dump(existing_data, f, ensure_ascii=False, indent=2)
            print(f"帖子详细信息已保存到: {comment_file}")
            
            # 发送数据到Kafka
            for item in context_data:
                kafka_data = {
                    'type': 'context',
                    'thread_id': item['thread_id'],
                    'title': item['title'],
                    'author': item['author'],
                    'replies': item['replies'],
                    'post_date': item['post_date'],
                    'url': item['url'],
                    'crawl_time': datetime.now().isoformat()
                }
                self._send_to_kafka(kafka_data)
            
            for item in comment_data:
                kafka_data = {
                    'type': item['type'],
                    'thread_id': item['thread_id'],
                    'author': item['author'],
                    'content': item['content'],
                    'crawl_time': datetime.now().isoformat()
                }
                self._send_to_kafka(kafka_data)
        except Exception as e:
            print(f"保存帖子详细信息时出错: {e}")
    
    async def get_post_detail(self, context, post):
        """获取帖子详情和回复（支持翻页）"""
        thread_id = post['thread_id']
        
        try:
            page = await context.new_page()
            replies = []
            page_num = 1
            max_pages = 10  # 限制最大翻页数，避免爬取过多
            has_next_page = True
            main_content = f"帖子内容（ID: {thread_id}）"
            
            while page_num <= max_pages and has_next_page:
                # 构建帖子详情URL
                full_url = self._build_post_detail_url(post, thread_id, page_num)
                print(f"访问帖子详情页 {page_num}: {full_url}")
                
                await page.goto(full_url, timeout=30000)
                await page.wait_for_load_state('networkidle', timeout=30000)
                
                content = await page.content()
                
                # 检查帖子是否被锁定
                if '此帖子被锁定' in content:
                    print(f"帖子 {thread_id} 被锁定，跳过")
                    await page.close()
                    return self._create_post_data(thread_id, post, f"帖子被锁定（ID: {thread_id}）", [])
                
                soup = BeautifulSoup(content, 'html.parser')
                
                # 第一页提取主贴内容
                if page_num == 1:
                    main_content = self._extract_main_content(soup, thread_id)
                
                # 提取回复
                print(f"开始提取第 {page_num} 页回复...")
                
                # 提取热点回复（只在第一页）
                if page_num == 1:
                    replies.extend(self._extract_hot_replies(soup))
                
                # 提取普通回复
                replies.extend(self._extract_normal_replies(soup, page_num))
                
                # 检查是否有下一页
                has_next_page = self._has_next_page(soup)
                
                if not has_next_page:
                    print("没有更多回复页")
                    break
                
                page_num += 1
                # 添加延迟
                await self._random_delay(1, 2)
            
            await page.close()
            
            print(f"总共找到 {len(replies)} 个回复")
            
            return self._create_post_data(thread_id, post, main_content, replies)
        except Exception as e:
            print(f"获取帖子详情时出错: {e}")
            # 如果获取失败，返回基本信息
            return self._create_post_data(thread_id, post, f"帖子内容（ID: {thread_id}）", [])
    
    def _build_post_detail_url(self, post, thread_id, page_num):
        """构建帖子详情URL"""
        if 'bbs.nga.cn' in post.get('url', ''):
            return f'https://bbs.nga.cn/read.php?tid={thread_id}&page={page_num}'
        else:
            return f'{self.base_url}/read.php?tid={thread_id}&page={page_num}'
    
    def _extract_main_content(self, soup, thread_id):
        """提取主贴内容"""
        content_elem = soup.select_one('.t_f')
        if not content_elem:
            content_elem = soup.select_one('.postcontent')
        
        if content_elem:
            main_content = content_elem.get_text(strip=True)
            print(f"提取到主贴内容，长度: {len(main_content)}")
        else:
            main_content = f"帖子内容（ID: {thread_id}）"
            print("未找到主贴内容，使用占位符")
        
        return main_content
    
    def _extract_hot_replies(self, soup):
        """提取热点回复"""
        replies = []
        comment_elems = soup.find_all('div', class_='comment_c')
        print(f"方式1 - 找到 {len(comment_elems)} 个热点回复元素")
        
        for comment_elem in comment_elems:
            try:
                author = '未知'
                author_elem = comment_elem.find('a', class_='userlink')
                if author_elem:
                    author = author_elem.get_text(strip=True)
                
                reply_content = ''
                content_elem = comment_elem.find(class_='ubbcode')
                if content_elem:
                    reply_content = content_elem.get_text(strip=True)
                    # 移除最后的"…… [原帖]"
                    reply_content = reply_content.replace('…… [原帖]', '').strip()
                
                if reply_content:
                    replies.append({
                        'author': author,
                        'content': reply_content
                    })
            except Exception as e:
                print(f"提取热点回复时出错: {e}")
                continue
        
        return replies
    
    def _extract_normal_replies(self, soup, page_num):
        """提取普通回复"""
        replies = []
        post_elems = soup.find_all('tr', class_='postrow')
        print(f"方式2 - 找到 {len(post_elems)} 个普通回复元素")
        
        for i, post_elem in enumerate(post_elems, 1):
            # 跳过主贴（通常是第一个）
            if page_num == 1 and i == 1:
                continue
            
            try:
                author = '未知'
                author_elem = post_elem.find('a', class_='userlink')
                if author_elem:
                    author = author_elem.get_text(strip=True)
                
                reply_content = ''
                content_elem = post_elem.find(class_='postcontent')
                if not content_elem:
                    content_elem = post_elem.find(class_='ubbcode')
                
                if content_elem:
                    reply_content = content_elem.get_text(strip=True)
                
                if reply_content:
                    replies.append({
                        'author': author,
                        'content': reply_content
                    })
            except Exception as e:
                print(f"提取普通回复时出错: {e}")
                continue
        
        return replies
    
    def _has_next_page(self, soup):
        """检查是否有下一页"""
        # 方式1: 查找文本为"下一页"的链接
        next_page = soup.find('a', text='下一页')
        if next_page:
            print(f"找到下一页链接（方式1）: {next_page.get('href', '')}")
            return True
        
        # 方式2: 查找包含"page="的链接
        page_links = soup.find_all('a', href=re.compile(r'page=\d+'))
        for link in page_links:
            link_text = link.get_text(strip=True)
            if '下一页' in link_text or '>' in link_text:
                print(f"找到下一页链接（方式2）: {link.get('href', '')}")
                return True
        
        # 方式3: 查找分页区域
        pagination = soup.find('div', class_='pages')
        if pagination:
            page_links = pagination.find_all('a')
            for link in page_links:
                link_text = link.get_text(strip=True)
                if '下一页' in link_text or '>' in link_text:
                    print(f"找到下一页链接（方式3）: {link.get('href', '')}")
                    return True
        
        return False
    
    def _create_post_data(self, thread_id, post, content, replies):
        """创建帖子数据"""
        return {
            'thread_id': thread_id,
            'title': post['title'],
            'author': post['author'],
            'content': content,
            'replies': replies
        }
    
    async def _random_delay(self, min_delay, max_delay):
        """随机延迟，避免被反爬虫"""
        delay = random.uniform(min_delay, max_delay)
        await asyncio.sleep(delay)
    
    def _get_last_crawl_time(self):
        """获取上次爬取时间"""
        if os.path.exists(self.last_crawl_time_file):
            try:
                with open(self.last_crawl_time_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    last_crawl_time_str = data.get('last_crawl_time')
                    if last_crawl_time_str:
                        return datetime.fromisoformat(last_crawl_time_str)
            except Exception as e:
                print(f"加载上次爬取时间时出错: {e}")
        return None

    def load_recent_tids(self, keyword):
        """加载最近的tid列表（按关键词）"""
        tid_file = os.path.join(self.output_dir, f'recent_tids_{keyword}.json')
        if os.path.exists(tid_file):
            try:
                with open(tid_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('recent_tids', [])
            except Exception as e:
                print(f"加载tid列表时出错: {e}")
        return []
    
    def save_recent_tids(self, keyword, tids):
        """保存最近的tid列表，最多保存50个（按关键词）"""
        recent_tids = tids[-50:]  # 只保留最近50个tid
        tid_file = os.path.join(self.output_dir, f'recent_tids_{keyword}.json')
        try:
            with open(tid_file, 'w', encoding='utf-8') as f:
                json.dump({'recent_tids': recent_tids}, f, ensure_ascii=False, indent=2)
            print(f"已保存 {len(recent_tids)} 个最近的tid")
        except Exception as e:
            print(f"保存tid列表时出错: {e}")
    
    def save_last_crawl_time(self):
        """保存上次爬取时间"""
        try:
            last_crawl_time = datetime.now().isoformat()
            with open(self.last_crawl_time_file, 'w', encoding='utf-8') as f:
                json.dump({'last_crawl_time': last_crawl_time}, f, ensure_ascii=False, indent=2)
            print(f"已保存上次爬取时间: {last_crawl_time}")
        except Exception as e:
            print(f"保存上次爬取时间时出错: {e}")
    
    def save_status(self):
        """保存爬取状态"""
        try:
            with open(self.status_file, 'w', encoding='utf-8') as f:
                json.dump(self.current_status, f, ensure_ascii=False, indent=2)
            print(f"已保存爬取状态: {self.current_status}")
        except Exception as e:
            print(f"保存状态时出错: {e}")
    
    def load_status(self):
        """加载爬取状态"""
        if os.path.exists(self.status_file):
            try:
                with open(self.status_file, 'r', encoding='utf-8') as f:
                    self.current_status = json.load(f)
                print(f"已加载爬取状态: {self.current_status}")
                return True
            except Exception as e:
                print(f"加载状态时出错: {e}")
        return False

def load_config():
    """加载配置文件"""
    config_path = 'config.json'
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        return {
            "cookies": {},
            "keywords": ["魔兽世界"]
        }

async def main():
    try:
        config = load_config()
        crawler = NGACrawlerPlaywright(config)
        await crawler.run()
    except Exception as e:
        print(f"运行爬虫时出错: {e}")

if __name__ == "__main__":
    asyncio.run(main())