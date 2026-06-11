-- author_stats 表建表语句
-- 用于存储作者的历史统计特征（平均热度、平均互动、发文数）

CREATE TABLE IF NOT EXISTS author_stats (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='作者统计信息表';