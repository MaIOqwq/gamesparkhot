#!/usr/bin/env python3
"""
作者统计信息更新脚本
功能：从 standardized_data 表统计作者信息并更新到 author_stats 表
支持全量初始化和增量更新两种模式
"""

import pymysql
import logging
import argparse
import configparser
import os
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class AuthorStatsUpdater:
    def __init__(self, config_path: str = 'config.ini'):
        self.config = self._load_config(config_path)
        self.conn: Optional[pymysql.Connection] = None

    def _load_config(self, config_path: str) -> configparser.ConfigParser:
        config = configparser.ConfigParser()
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        config.read(config_path, encoding='utf-8')
        return config

    def get_connection(self) -> pymysql.Connection:
        return pymysql.connect(
            host=self.config.get('database', 'host', fallback=os.getenv('DB_HOST', 'localhost')),
            port=self.config.getint('database', 'port', fallback=3306),
            user=self.config.get('database', 'user', fallback=os.getenv('DB_USER', 'spark')),
            password=self.config.get('database', 'password', fallback=os.getenv('DB_PASSWORD', 'your_db_password')),
            database=self.config.get('database', 'database', fallback=os.getenv('DB_NAME', 'standardized_data')),
            charset='utf8mb4',
            connect_timeout=10,
            read_timeout=300,
            write_timeout=300
        )

    def init_connection(self):
        self.conn = self.get_connection()
        logger.info("数据库连接成功")

    def close_connection(self):
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.info("数据库连接已关闭")

    def create_author_stats_table(self):
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS author_stats (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            author VARCHAR(128) NOT NULL COMMENT '作者名称',
            platform TINYINT NOT NULL COMMENT '平台：1=B站，0=NGA',
            avg_hot DOUBLE NOT NULL DEFAULT 0 COMMENT '平均热度',
            avg_like DOUBLE NOT NULL DEFAULT 0 COMMENT '平均点赞数',
            avg_comment DOUBLE NOT NULL DEFAULT 0 COMMENT '平均评论数',
            post_count INT NOT NULL DEFAULT 0 COMMENT '发文数',
            last_updated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            UNIQUE KEY uk_author_platform (author, platform),
            KEY idx_platform (platform),
            KEY idx_post_count (post_count)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='作者统计信息表'
        """
        with self.conn.cursor() as cursor:
            cursor.execute(create_table_sql)
        self.conn.commit()
        logger.info("author_stats 表创建成功")

    def full_update(self):
        logger.info("开始全量更新...")
        start_time = datetime.now()

        truncate_sql = "TRUNCATE TABLE author_stats"
        with self.conn.cursor() as cursor:
            cursor.execute(truncate_sql)
        self.conn.commit()
        logger.info("已清空 author_stats 表")

        stats_sql = """
        INSERT INTO author_stats (author, platform, avg_hot, avg_like, avg_comment, post_count)
        SELECT
            author,
            platform,
            COALESCE(AVG(hot_score), 0) as avg_hot,
            COALESCE(AVG(like_count), 0) as avg_like,
            COALESCE(AVG(comment_count), 0) as avg_comment,
            COUNT(*) as post_count
        FROM standardized_data
        GROUP BY author, platform
        """

        with self.conn.cursor() as cursor:
            affected_rows = cursor.execute(stats_sql)

        self.conn.commit()

        end_time = datetime.now()
        elapsed = (end_time - start_time).total_seconds()

        logger.info(f"全量更新完成: 影响行数={affected_rows}, 耗时={elapsed:.2f}秒")

    def incremental_update(self):
        logger.info("开始增量更新...")
        start_time = datetime.now()

        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        logger.info(f"增量更新范围: {yesterday}")

        find_authors_sql = """
        SELECT DISTINCT author, platform
        FROM standardized_data
        WHERE DATE(created_at) = %s
        """

        with self.conn.cursor() as cursor:
            cursor.execute(find_authors_sql, (yesterday,))
            authors = cursor.fetchall()

        if not authors:
            logger.info(f"昨天({yesterday})没有新增数据，退出增量更新")
            return

        logger.info(f"发现 {len(authors)} 个作者有新增数据")

        stats_sql = """
        INSERT INTO author_stats (author, platform, avg_hot, avg_like, avg_comment, post_count)
        SELECT
            author,
            platform,
            COALESCE(AVG(hot_score), 0) as avg_hot,
            COALESCE(AVG(like_count), 0) as avg_like,
            COALESCE(AVG(comment_count), 0) as avg_comment,
            COUNT(*) as post_count
        FROM standardized_data
        WHERE author = %s AND platform = %s
        GROUP BY author, platform
        ON DUPLICATE KEY UPDATE
            avg_hot = VALUES(avg_hot),
            avg_like = VALUES(avg_like),
            avg_comment = VALUES(avg_comment),
            post_count = VALUES(post_count),
            last_updated = CURRENT_TIMESTAMP
        """

        total_affected = 0
        with self.conn.cursor() as cursor:
            for author, platform in authors:
                try:
                    cursor.execute(stats_sql, (author, platform))
                    total_affected += cursor.rowcount
                except Exception as e:
                    logger.error(f"更新作者 {author} (platform={platform}) 失败: {e}")
                    continue

        self.conn.commit()

        end_time = datetime.now()
        elapsed = (end_time - start_time).total_seconds()

        logger.info(f"增量更新完成: 处理作者数={len(authors)}, 影响行数={total_affected}, 耗时={elapsed:.2f}秒")

    def get_stats_count(self) -> int:
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM author_stats")
            result = cursor.fetchone()
            return result[0] if result else 0

    def verify_data(self):
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM author_stats")
            total = cursor.fetchone()[0]

            cursor.execute("SELECT platform, COUNT(*) FROM author_stats GROUP BY platform")
            by_platform = cursor.fetchall()

            logger.info(f"author_stats 表当前数据: 总数={total}")
            for platform, count in by_platform:
                platform_name = "B站" if platform == 1 else "NGA"
                logger.info(f"  - {platform_name}: {count} 条")

    def run(self, full_mode: bool = False):
        try:
            self.init_connection()

            self.create_author_stats_table()

            if full_mode:
                self.full_update()
            else:
                self.incremental_update()

            self.verify_data()

            logger.info("脚本执行成功")
            return 0

        except pymysql.Error as e:
            logger.error(f"数据库错误: {e}")
            return 1
        except FileNotFoundError as e:
            logger.error(f"配置文件错误: {e}")
            return 1
        except Exception as e:
            logger.error(f"未知错误: {e}")
            return 1
        finally:
            self.close_connection()


def main():
    parser = argparse.ArgumentParser(
        description='作者统计信息更新脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python update_author_stats.py              # 增量更新（默认）
  python update_author_stats.py --full       # 全量初始化
  python update_author_stats.py --config /path/to/config.ini  # 指定配置文件
        """
    )
    parser.add_argument(
        '--full',
        action='store_true',
        help='全量初始化模式（清空表并重新统计所有作者）'
    )
    parser.add_argument(
        '--config',
        default='config.ini',
        help='配置文件路径（默认: config.ini）'
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("作者统计信息更新脚本启动")
    logger.info(f"运行模式: {'全量初始化' if args.full else '增量更新'}")
    logger.info("=" * 60)

    updater = AuthorStatsUpdater(config_path=args.config)
    exit_code = updater.run(full_mode=args.full)

    logger.info("=" * 60)
    logger.info(f"脚本结束，退出码: {exit_code}")
    logger.info("=" * 60)

    exit(exit_code)


if __name__ == '__main__':
    main()