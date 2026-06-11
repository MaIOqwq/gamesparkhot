import pymysql
import json

class DatabaseInitializer:
    def __init__(self, config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        self.db_config = config.get('database', {})
    
    def init_database(self):
        """初始化数据库"""
        if not self.db_config.get('enabled', False):
            print("数据库未启用，跳过初始化")
            return
        
        try:
            # 连接数据库
            conn = pymysql.connect(
                host=self.db_config.get('host', 'localhost'),
                port=self.db_config.get('port', 3306),
                user=self.db_config.get('user', 'root'),
                password=self.db_config.get('password', ''),
                charset=self.db_config.get('charset', 'utf8mb4')
            )
            
            with conn.cursor() as cursor:
                # 创建数据库
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.db_config.get('database', 'crawler_data')} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                
                # 切换到数据库
                cursor.execute(f"USE {self.db_config.get('database', 'crawler_data')}")
                
                # 创建NGA帖子表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS nga_posts (
                        id INT PRIMARY KEY AUTO_INCREMENT,
                        thread_id VARCHAR(50) UNIQUE,
                        author VARCHAR(128) NOT NULL,
                        title VARCHAR(255) NOT NULL,
                        content TEXT,
                        post_time DATETIME,
                        keyword VARCHAR(100) NOT NULL,
                        replies INT DEFAULT 0,
                        view_count INT DEFAULT 0,
                        like_count INT DEFAULT 0,
                        floor INT DEFAULT 0,
                        quote TEXT,
                        is_hot_reply BOOLEAN DEFAULT FALSE,
                        author_level INT DEFAULT 0,
                        author_post_count INT DEFAULT 0,
                        board_name VARCHAR(100),
                        has_image BOOLEAN DEFAULT FALSE,
                        has_video BOOLEAN DEFAULT FALSE,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                ''')
                
                # 创建B站视频表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS bilibili_videos (
                        id INT PRIMARY KEY AUTO_INCREMENT,
                        bvid VARCHAR(50) UNIQUE,
                        up_name VARCHAR(128) NOT NULL,
                        title VARCHAR(255) NOT NULL,
                        desc TEXT,
                        pubdate DATETIME,
                        keyword VARCHAR(100) NOT NULL,
                        video_play_count INT DEFAULT 0,
                        liked_count INT DEFAULT 0,
                        video_comment INT DEFAULT 0,
                        video_coin_count INT DEFAULT 0,
                        video_favorite_count INT DEFAULT 0,
                        video_share_count INT DEFAULT 0,
                        video_danmaku INT DEFAULT 0,
                        up_fans INT DEFAULT 0,
                        up_total_videos INT DEFAULT 0,
                        up_level INT DEFAULT 0,
                        mid VARCHAR(50),
                        has_image BOOLEAN DEFAULT FALSE,
                        has_video BOOLEAN DEFAULT TRUE,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                ''')
                
                # 创建作者统计表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS author_stats (
                        id INT PRIMARY KEY AUTO_INCREMENT,
                        author VARCHAR(128) NOT NULL,
                        platform TINYINT NOT NULL,
                        avg_hot FLOAT DEFAULT 0.0,
                        avg_like FLOAT DEFAULT 0.0,
                        avg_comment FLOAT DEFAULT 0.0,
                        post_count INT DEFAULT 0,
                        last_update DATETIME DEFAULT CURRENT_TIMESTAMP,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        UNIQUE KEY unique_author_platform (author, platform)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                ''')
            
            conn.commit()
            print("数据库初始化成功")
        except Exception as e:
            print(f"数据库初始化失败: {e}")
        finally:
            if conn:
                conn.close()

if __name__ == "__main__":
    initializer = DatabaseInitializer('config.json')
    initializer.init_database()