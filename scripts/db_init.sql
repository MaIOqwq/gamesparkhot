-- 创建数据库
CREATE DATABASE IF NOT EXISTS yuqing_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE yuqing_db;

-- 创建关键词表
CREATE TABLE IF NOT EXISTS keyword (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(50) NOT NULL UNIQUE,
    hot INT NOT NULL DEFAULT 0,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 创建热门内容表
CREATE TABLE IF NOT EXISTS hot_content (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    platform VARCHAR(20) NOT NULL,
    hot INT NOT NULL DEFAULT 0,
    keyword VARCHAR(50) NOT NULL,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建词云数据表
CREATE TABLE IF NOT EXISTS word_cloud_data (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    word VARCHAR(50) NOT NULL,
    value INT NOT NULL DEFAULT 0,
    keyword VARCHAR(50) NOT NULL,
    type VARCHAR(20),
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建平台数据表
CREATE TABLE IF NOT EXISTS platform_data (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    platform VARCHAR(20) NOT NULL,
    count INT NOT NULL DEFAULT 0,
    keyword VARCHAR(50) NOT NULL,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建趋势数据表
CREATE TABLE IF NOT EXISTS trend_data (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    time_point VARCHAR(20) NOT NULL,
    value INT NOT NULL DEFAULT 0,
    keyword VARCHAR(50) NOT NULL,
    is_predict BOOLEAN DEFAULT FALSE,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 插入示例数据
INSERT INTO keyword (name, hot) VALUES
('手机游戏', 1000),
('王者荣耀', 850),
('原神', 920),
('和平精英', 780),
('崩坏：星穹铁道', 720);

-- 插入平台数据
INSERT INTO platform_data (platform, count, keyword) VALUES
('bilibili', 6500, '手机游戏'),
('nga', 3500, '手机游戏');

-- 插入热门内容
INSERT INTO hot_content (title, platform, hot, keyword) VALUES
('原神新版本更新内容详解', 'bilibili', 15678, '手机游戏'),
('王者荣耀新赛季平衡调整分析', 'nga', 12345, '手机游戏'),
('和平精英新地图测评', 'bilibili', 9876, '手机游戏'),
('崩坏：星穹铁道新角色强度讨论', 'nga', 8765, '手机游戏'),
('手机游戏市场分析报告', 'bilibili', 7654, '手机游戏');

-- 插入词云数据
INSERT INTO word_cloud_data (word, value, keyword, type) VALUES
('原神', 1200, '手机游戏', 'overall'),
('王者荣耀', 1100, '手机游戏', 'overall'),
('和平精英', 950, '手机游戏', 'overall'),
('崩坏：星穹铁道', 880, '手机游戏', 'overall'),
('明日方舟', 750, '手机游戏', 'overall'),
('好评', 600, '手机游戏', 'sentiment'),
('好玩', 550, '手机游戏', 'sentiment'),
('优秀', 500, '手机游戏', 'sentiment'),
('失望', 400, '手机游戏', 'sentiment'),
('差评', 350, '手机游戏', 'sentiment');

-- 插入趋势数据
INSERT INTO trend_data (time_point, value, keyword, is_predict) VALUES
('00:00', 120, '手机游戏', FALSE),
('03:00', 132, '手机游戏', FALSE),
('06:00', 101, '手机游戏', FALSE),
('09:00', 134, '手机游戏', FALSE),
('12:00', 90, '手机游戏', FALSE),
('15:00', 230, '手机游戏', FALSE),
('18:00', 210, '手机游戏', FALSE),
('21:00', 180, '手机游戏', FALSE),
('00:00', 170, '手机游戏', TRUE),
('03:00', 150, '手机游戏', TRUE),
('06:00', 130, '手机游戏', TRUE),
('09:00', 110, '手机游戏', TRUE);
