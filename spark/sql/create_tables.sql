-- 创建标准化数据表
-- 根据数据流.md中的字段定义

-- 创建数据库
CREATE DATABASE IF NOT EXISTS standardized_data DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE standardized_data;

-- 创建标准化数据表
CREATE TABLE IF NOT EXISTS standardized_data (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
    raw_id BIGINT NOT NULL COMMENT '关联爬虫原始数据ID',
    platform VARCHAR(20) NOT NULL COMMENT '平台：bilibili或nga',
    title_clean VARCHAR(500) COMMENT '清洗后标题（去特殊符号、停用词）',
    content_clean TEXT COMMENT '清洗后正文（分词、去重、过滤）',
    view_count INT DEFAULT 0 COMMENT '标准化播放量',
    like_count INT DEFAULT 0 COMMENT '标准化点赞数',
    coin_count INT DEFAULT 0 COMMENT '标准化投币数',
    favorite_count INT DEFAULT 0 COMMENT '标准化收藏数',
    share_count INT DEFAULT 0 COMMENT '标准化分享数',
    comment_count INT DEFAULT 0 COMMENT '标准化评论数',
    publish_time DATETIME COMMENT '标准化发布时间',
    time_diff DOUBLE COMMENT '发布时长（小时）',
    hot_raw DOUBLE COMMENT '原始热度计算值',
    hot_norm DOUBLE COMMENT '归一化热度值',
    hot_score DOUBLE COMMENT '最终统一热度值',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    
    -- 索引
    INDEX idx_raw_id (raw_id),
    INDEX idx_platform (platform),
    INDEX idx_publish_time (publish_time),
    INDEX idx_hot_score (hot_score),
    INDEX idx_created_at (created_at),
    UNIQUE KEY uk_raw_id_platform (raw_id, platform)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='标准化数据表';

-- 创建B站原始数据表（用于存储原始爬虫数据）
CREATE TABLE IF NOT EXISTS bili_raw_data (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
    video_id VARCHAR(50) COMMENT '视频ID',
    user_id VARCHAR(50) COMMENT 'UP主ID',
    title VARCHAR(500) COMMENT '视频标题',
    `desc` VARCHAR(500) COMMENT '视频描述',
    create_time BIGINT COMMENT '发布时间（时间戳）',
    video_play_count INT COMMENT '播放量',
    video_favorite_count INT COMMENT '收藏数',
    video_share_count INT COMMENT '分享数',
    video_coin_count INT COMMENT '投币数',
    video_danmaku INT COMMENT '弹幕数',
    video_comment INT COMMENT '评论数',
    liked_count INT COMMENT '点赞数',
    disliked_count INT COMMENT '点踩数',
    source_keyword VARCHAR(100) COMMENT '来源关键词',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    
    INDEX idx_video_id (video_id),
    INDEX idx_user_id (user_id),
    INDEX idx_source_keyword (source_keyword),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='B站原始数据表';

-- 创建B站评论原始数据表
CREATE TABLE IF NOT EXISTS bili_comment_raw_data (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
    comment_id VARCHAR(50) NOT NULL COMMENT '评论ID',
    video_id VARCHAR(50) COMMENT '视频ID',
    user_id VARCHAR(50) COMMENT '评论用户ID',
    content TEXT COMMENT '评论内容',
    create_time BIGINT COMMENT '评论时间（时间戳）',
    like_count INT COMMENT '评论点赞数',
    source_keyword VARCHAR(100) COMMENT '来源关键词',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    
    INDEX idx_comment_id (comment_id),
    INDEX idx_video_id (video_id),
    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='B站评论原始数据表';

-- 创建NGA帖子原始数据表
CREATE TABLE IF NOT EXISTS nga_thread_raw_data (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
    thread_id VARCHAR(50) NOT NULL COMMENT '帖子唯一标识符',
    title VARCHAR(500) COMMENT '帖子标题',
    author VARCHAR(100) COMMENT '发帖作者用户名',
    replies INT COMMENT '回复数量',
    post_date DATE COMMENT '发帖日期',
    url VARCHAR(500) COMMENT '帖子完整链接',
    keyword VARCHAR(100) COMMENT '爬取关键词',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    
    INDEX idx_thread_id (thread_id),
    INDEX idx_author (author),
    INDEX idx_keyword (keyword),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='NGA帖子原始数据表';

-- 创建NGA内容原始数据表
CREATE TABLE IF NOT EXISTS nga_content_raw_data (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键，自增',
    thread_id VARCHAR(50) COMMENT '帖子唯一标识符',
    author VARCHAR(100) COMMENT '作者用户名',
    content TEXT COMMENT '内容文本',
    `type` VARCHAR(20) COMMENT '内容类型（main表示主贴，reply表示回复）',
    keyword VARCHAR(100) COMMENT '爬取关键词',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    
    INDEX idx_thread_id (thread_id),
    INDEX idx_author (author),
    INDEX idx_type (`type`),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='NGA内容原始数据表';

-- 授权用户访问
-- 根据实际情况修改用户名和密码
-- GRANT ALL PRIVILEGES ON standardized_data.* TO 'spark_user'@'%';
-- FLUSH PRIVILEGES;