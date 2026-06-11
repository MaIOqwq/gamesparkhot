import requests
import re
import json
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urlencode, unquote

class NGACrawler:
    def __init__(self, cookies):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        }
        self.session.headers.update(self.headers)
        self.set_cookies(cookies)
        self.base_url = 'https://ngabbs.com'
    
    def set_cookies(self, cookies):
        """设置登录cookie"""
        if isinstance(cookies, dict):
            for key, value in cookies.items():
                self.session.cookies.set(key, value)
        elif isinstance(cookies, str):
            for cookie in cookies.split(';'):
                if cookie.strip():
                    key, value = cookie.strip().split('=', 1)
                    self.session.cookies.set(key, value)
    
    def search_posts(self, keyword, page=1):
        """搜索关键词相关帖子"""
        search_url = f'{self.base_url}/thread.php'
        params = {
            'fid': '75',  # 综合讨论区，可根据需要修改
            'keyword': keyword,
            'page': page
        }
        
        response = self.session.get(search_url, params=params)
        self._check_response(response)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        posts = []
        
        # 解析搜索结果
        for thread_item in soup.select('.topicrow'):
            try:
                title_elem = thread_item.select_one('.topic a')
                if not title_elem:
                    continue
                
                title = title_elem.get_text(strip=True)
                thread_url = title_elem['href']
                thread_id = re.search(r'tid=(\d+)', thread_url).group(1) if 'tid=' in thread_url else None
                
                author_elem = thread_item.select_one('.author')
                author = author_elem.get_text(strip=True) if author_elem else '未知'
                
                reply_elem = thread_item.select_one('.replies')
                replies = reply_elem.get_text(strip=True) if reply_elem else '0'
                
                posts.append({
                    'title': title,
                    'thread_id': thread_id,
                    'url': f'{self.base_url}/{thread_url}' if thread_url.startswith('thread') else thread_url,
                    'author': author,
                    'replies': replies
                })
            except Exception as e:
                print(f"解析帖子时出错: {e}")
                continue
        
        return posts
    
    def get_post_detail(self, thread_id, page=1):
        """获取帖子详情和回复"""
        post_url = f'{self.base_url}/thread.php'
        params = {
            'tid': thread_id,
            'page': page
        }
        
        response = self.session.get(post_url, params=params)
        self._check_response(response)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        post_data = {
            'thread_id': thread_id,
            'title': '',
            'author': '',
            'content': '',
            'replies': []
        }
        
        # 解析主贴
        main_post = soup.select_one('.post')
        if main_post:
            title_elem = soup.select_one('.topic_title')
            post_data['title'] = title_elem.get_text(strip=True) if title_elem else ''
            
            author_elem = main_post.select_one('.author')
            post_data['author'] = author_elem.get_text(strip=True) if author_elem else ''
            
            content_elem = main_post.select_one('.postcontent')
            post_data['content'] = content_elem.get_text(strip=True) if content_elem else ''
        
        # 解析回复
        for reply in soup.select('.post.reply'):
            try:
                reply_author_elem = reply.select_one('.author')
                reply_author = reply_author_elem.get_text(strip=True) if reply_author_elem else '未知'
                
                reply_content_elem = reply.select_one('.postcontent')
                reply_content = reply_content_elem.get_text(strip=True) if reply_content_elem else ''
                
                post_data['replies'].append({
                    'author': reply_author,
                    'content': reply_content
                })
            except Exception as e:
                print(f"解析回复时出错: {e}")
                continue
        
        return post_data
    
    def _check_response(self, response):
        """检查响应是否正常"""
        if response.status_code != 200:
            raise Exception(f"请求失败，状态码: {response.status_code}")
        
        # 检查是否被反爬虫
        if '您的请求过于频繁' in response.text or '请输入验证码' in response.text:
            raise Exception("被反爬虫机制拦截，请稍后再试")
    
    def _random_delay(self):
        """随机延迟，避免被反爬虫"""
        time.sleep(random.uniform(1, 3))

def main():
    # 请替换为您的NGA登录cookie
    cookies = {
        # 示例cookie，实际使用时需要替换
        # 'ngacn0comUserInfo': '...',
        # 'ngacn0comUserInfoCheck': '...',
        # 'ngacn0comPassportUrl': '...'
    }
    
    # 或者使用字符串形式的cookie
    # cookies = 'ngacn0comUserInfo=...; ngacn0comUserInfoCheck=...;'
    
    crawler = NGACrawler(cookies)
    
    # 搜索关键词
    keyword = input("请输入搜索关键词: ")
    
    # 获取搜索结果
    print(f"正在搜索关键词: {keyword}")
    posts = crawler.search_posts(keyword)
    
    if not posts:
        print("未找到相关帖子")
        return
    
    print(f"找到 {len(posts)} 个相关帖子:")
    for i, post in enumerate(posts, 1):
        print(f"{i}. {post['title']} - 作者: {post['author']} - 回复数: {post['replies']}")
    
    # 选择要爬取的帖子
    choice = int(input("请输入要爬取的帖子序号: ")) - 1
    if 0 <= choice < len(posts):
        selected_post = posts[choice]
        print(f"\n正在爬取帖子: {selected_post['title']}")
        
        # 获取帖子详情和回复
        post_detail = crawler.get_post_detail(selected_post['thread_id'])
        
        # 保存数据
        output_file = f"nga_post_{selected_post['thread_id']}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(post_detail, f, ensure_ascii=False, indent=2)
        
        print(f"\n爬取完成，数据已保存到: {output_file}")
        print(f"帖子标题: {post_detail['title']}")
        print(f"作者: {post_detail['author']}")
        print(f"主贴内容: {post_detail['content'][:100]}...")
        print(f"回复数: {len(post_detail['replies'])}")
    else:
        print("无效的选择")

if __name__ == "__main__":
    main()
