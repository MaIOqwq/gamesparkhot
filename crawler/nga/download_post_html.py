import asyncio
from playwright.async_api import async_playwright
import json

async def download_post_html():
    """下载一个帖子的HTML页面"""
    try:
        # 加载配置
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        cookies = config.get('cookies', {})
        base_url = 'https://ngabbs.com'
        
        # 选择一个有回复的帖子
        thread_id = '46132807'  # 跟风玩了终末地。。国产二游都是这种池子吗？？
        post_url = f'{base_url}/read.php?tid={thread_id}&page=1'
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            
            # 设置cookie
            if cookies:
                cookie_list = []
                for key, value in cookies.items():
                    if value:
                        cookie_list.append({
                            'name': key,
                            'value': value,
                            'url': base_url
                        })
                
                if cookie_list:
                    await context.add_cookies(cookie_list)
                    print("已设置cookie")
            
            # 访问帖子
            page = await context.new_page()
            print(f"正在访问帖子: {post_url}")
            await page.goto(post_url)
            await page.wait_for_load_state('networkidle')
            
            # 获取页面内容
            content = await page.content()
            
            # 保存HTML到文件
            with open(f'post_{thread_id}.html', 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"帖子HTML已保存到: post_{thread_id}.html")
            
            await page.close()
            await browser.close()
            
    except Exception as e:
        print(f"下载帖子时出错: {e}")

if __name__ == "__main__":
    asyncio.run(download_post_html())