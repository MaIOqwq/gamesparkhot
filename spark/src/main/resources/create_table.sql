-- 创建标准化数据表
CREATE TABLE IF NOT EXISTS standardized_data (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    raw_id VARCHAR(64) NOT NULL,
    platform TINYINT NOT NULL COMMENT '1=B站，0=NGA',
    type VARCHAR(16) COMMENT '内容类型',
    author VARCHAR(128) NOT NULL COMMENT '作者',
    title_clean VARCHAR(500) COMMENT '清洗后标题',
    content_clean TEXT COMMENT '清洗后内容',
    publish_time DATETIME NOT NULL COMMENT '发布时间',
    keyword VARCHAR(100) NOT NULL COMMENT '关键词',
    view_count INT DEFAULT 0 COMMENT '播放/查看量',
    like_count INT DEFAULT 0 COMMENT '点赞数',
    comment_count INT DEFAULT 0 COMMENT '评论/回复数',
    coin_count INT DEFAULT 0 COMMENT '投币数',
    favorite_count INT DEFAULT 0 COMMENT '收藏数',
    share_count INT DEFAULT 0 COMMENT '分享数',
    danmaku_count INT DEFAULT 0 COMMENT '弹幕数',
    is_hot_reply TINYINT DEFAULT 0 COMMENT '是否热点回复',
    author_fans INT DEFAULT 0 COMMENT '作者粉丝数',
    author_level INT DEFAULT 0 COMMENT '作者等级',
    author_post_count INT DEFAULT 0 COMMENT '作者历史发文数',
    has_image TINYINT DEFAULT 0 COMMENT '是否含图片',
    has_video TINYINT DEFAULT 0 COMMENT '是否含视频',
    board_name VARCHAR(50) COMMENT '版块名称',
    hot_raw DOUBLE COMMENT '原始热度（加权和）',
    hot_norm DOUBLE COMMENT '归一化热度（0~1）',
    hot_score DOUBLE COMMENT '最终热度（当前等于hot_norm）',
    text_length INT DEFAULT 0 COMMENT '清洗后文本长度',
    sentiment_score FLOAT DEFAULT 0 COMMENT '情感得分',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',

    -- 唯一索引，避免重复数据
    UNIQUE KEY uk_platform_rawid (platform, raw_id),

    -- 优化查询性能的索引
    INDEX idx_keyword_publish (keyword, publish_time),
    INDEX idx_publish_time (publish_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='标准化数据表';

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS standardized_data CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 使用数据库
USE standardized_data;

-- ============================================================
-- 回访系统相关表
-- ============================================================

-- 互动指标时序表（每次回访追加一条记录）
CREATE TABLE IF NOT EXISTS content_metrics (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    raw_id VARCHAR(64) NOT NULL COMMENT '关联 standardized_data.raw_id',
    platform TINYINT NOT NULL COMMENT '1=B站，0=NGA',
    captured_at DATETIME NOT NULL COMMENT '本次回访时间',
    comment_count INT DEFAULT 0 COMMENT '当前评论数',
    like_count INT DEFAULT 0 COMMENT '当前点赞数',
    coin_count INT DEFAULT 0 COMMENT '当前投币数',
    favorite_count INT DEFAULT 0 COMMENT '当前收藏数',
    share_count INT DEFAULT 0 COMMENT '当前分享数',
    view_count INT DEFAULT 0 COMMENT '当前播放量',
    hot_raw DOUBLE DEFAULT 0 COMMENT '当前原始热度',
    hot_score DOUBLE DEFAULT 0 COMMENT '当前热度评分',
    lambda DOUBLE DEFAULT 0 COMMENT '本次计算的 λ 值',
    revisit_level INT DEFAULT 0 COMMENT '回访级别',
    INDEX idx_raw_id (raw_id),
    INDEX idx_captured_at (captured_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='内容指标时序表';

-- 回访队列表
CREATE TABLE IF NOT EXISTS crawl_queue (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    raw_id VARCHAR(64) NOT NULL COMMENT '关联 standardized_data.raw_id',
    platform TINYINT NOT NULL COMMENT '1=B站，0=NGA',
    url VARCHAR(500) NOT NULL COMMENT '内容链接',
    keyword VARCHAR(100) NOT NULL COMMENT '关键词',
    first_captured DATETIME NOT NULL COMMENT '首次抓取时间',
    last_visited DATETIME COMMENT '上次回访时间',
    next_visit DATETIME COMMENT '下次计划回访时间',
    current_lambda DOUBLE DEFAULT 0 COMMENT '当前 λ 值',
    revisit_level INT DEFAULT 0 COMMENT '0=首次, 1=爆款, 2=热门, 3=中等, 4=低活, -1=沉寂',
    last_comment_count INT DEFAULT 0 COMMENT '上次回访时的评论数',
    last_like_count INT DEFAULT 0,
    last_hot_raw DOUBLE DEFAULT 0 COMMENT '上次回访时的热度',
    last_rpid BIGINT DEFAULT 0 COMMENT '已拉取的最大回复ID（增量用）',
    status VARCHAR(16) DEFAULT 'active' COMMENT 'active / paused / dead',
    visit_count INT DEFAULT 0 COMMENT '已回访次数',
    UNIQUE KEY uk_raw_id (raw_id),
    INDEX idx_next_visit (next_visit),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='爬虫回访队列表';
