# 数据结构文档

本文档定义 GameOpinion 数据管道各阶段的输入输出格式。

---

## 1. Kafka 消息格式

### 1.1 Topic 列表

| Topic | 生产者 | 消费者 | 用途 |
|---|---|---|---|
| `crawler_data` | NGA 爬虫 (统一格式) | UnifiedDataCleaner | NGA 帖子/回复 |
| `bilibili_video` | B站爬虫 | BiliDataCleaner | B站视频 |
| `bilibili_comment` | B站爬虫 | BiliDataCleaner | B站评论 |
| `nga_context` | NGA 爬虫 (原始格式) | NgaDataCleaner | NGA 帖子元信息 |
| `nga_comment` | NGA 爬虫 (原始格式) | NgaDataCleaner | NGA 内容 |

所有消息为 UTF-8 JSON 字符串。

### 1.2 `crawler_data` — NGA 统一格式

**帖子 (type=post):**

```json
{
  "platform": "nga",
  "type": "post",
  "raw_id": "12345678",
  "author": "玩家A",
  "title": "原神新版本讨论",
  "content": "帖子全文...",
  "publish_time": "2025-03-20",
  "keyword": "手机游戏",
  "view_count": 0,
  "like_count": 0,
  "comment_count": "25",
  "coin_count": 0,
  "favorite_count": 0,
  "share_count": 0,
  "danmaku_count": 0,
  "is_hot_reply": false,
  "author_fans": 0,
  "author_level": 0,
  "author_post_count": 0,
  "has_image": false,
  "has_video": false,
  "board_name": ""
}
```

**回复 (type=reply):**

```json
{
  "platform": "nga",
  "type": "reply",
  "raw_id": "12345678",
  "author": "玩家B",
  "title": "原神新版本讨论",
  "content": "回复内容...",
  "publish_time": "2025-03-20",
  "keyword": "手机游戏",
  "view_count": 0,
  "like_count": 0,
  "comment_count": 0,
  "...": "其余字段同上，均为零值"
}
```

### 1.3 `bilibili_video` — B站视频

```json
{
  "video_id": "396850643",
  "user_id": "396850643",
  "title": "原神新版本更新内容",
  "desc": "视频描述",
  "create_time": 1700000000,
  "liked_count": 12345,
  "video_play_count": 50000,
  "video_favorite_count": 2000,
  "video_share_count": 1000,
  "video_coin_count": 3000,
  "video_danmaku": 500,
  "video_comment": 800,
  "source_keyword": "手机游戏",
  "raw_id": "396850643",
  "add_ts": 1700000000,
  "last_modify_ts": 1700000000
}
```

### 1.4 `bilibili_comment` — B站评论

```json
{
  "comment_id": "123456789",
  "video_id": "396850643",
  "user_id": "396850643",
  "content": "这个视频很有意思",
  "create_time": 1700000000,
  "like_count": "150",
  "sub_comment_count": "5",
  "parent_comment_id": "0",
  "source_keyword": "手机游戏",
  "add_ts": 1700000000,
  "last_modify_ts": 1700000000
}
```

### 1.5 `nga_context` / `nga_comment` — NGA 原始格式 (旧版)

**nga_context (帖子元信息):**

```json
{
  "type": "context",
  "thread_id": "12345678",
  "title": "原神新版本讨论",
  "author": "玩家A",
  "replies": "25",
  "post_date": "2025-03-20",
  "url": "https://ngabbs.com/read.php?tid=12345678",
  "crawl_time": "2025-03-20T10:30:00"
}
```

**nga_comment (主楼/回复):**

```json
{
  "type": "main",
  "thread_id": "12345678",
  "author": "玩家A",
  "content": "帖子或回复内容",
  "crawl_time": "2025-03-20T10:30:00"
}
```

---

## 2. Spark 清洗输出

UnifiedDataCleaner 消费 `crawler_data`，清洗后写入 MariaDB。输出字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `raw_id` | string | 源平台唯一 ID |
| `platform` | int | 1=B站, 0=NGA |
| `type` | string | post / reply |
| `author` | string | 作者名 |
| `title_clean` | string | 清洗后的标题 (去除 URL/HTML/特殊字符) |
| `content_clean` | text | 清洗后的正文 |
| `publish_time` | timestamp | 标准化为 `yyyy-MM-dd HH:mm:ss` |
| `keyword` | string | 搜索关键词 |
| `view_count` ~ `danmaku_count` | int | 各项互动指标 |
| `hot_raw` | double | `like + comment + coin + favorite + share` 加权和 |
| `hot_norm` | double | `log(1+hot_raw) / platform_cap`，B站上限 11.29，NGA 上限 3.26 |
| `hot_score` | double | 最终热度 = hot_norm × exp(-time_diff/24) |
| `text_length` | int | 清洗后文本长度 |
| `sentiment_score` | float | 来自情感分析服务 (localhost:8001)，范围 -1~1 |

---

## 3. MariaDB 表结构

数据库：`standardized_data`

### 3.1 `standardized_data` — 主数据表

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | BIGINT | PK AUTO_INCREMENT | |
| `raw_id` | VARCHAR(64) | NOT NULL | 平台唯一标识 |
| `platform` | TINYINT | NOT NULL | 1=B站, 0=NGA |
| `type` | VARCHAR(16) | | post/reply |
| `author` | VARCHAR(128) | NOT NULL | 作者名 |
| `title_clean` | VARCHAR(500) | | 清洗后标题 |
| `content_clean` | TEXT | | 清洗后正文 |
| `publish_time` | DATETIME | NOT NULL | 发布时间 |
| `keyword` | VARCHAR(100) | NOT NULL | 搜索关键词 |
| `view_count` | INT | DEFAULT 0 | |
| `like_count` | INT | DEFAULT 0 | |
| `comment_count` | INT | DEFAULT 0 | |
| `coin_count` | INT | DEFAULT 0 | |
| `favorite_count` | INT | DEFAULT 0 | |
| `share_count` | INT | DEFAULT 0 | |
| `danmaku_count` | INT | DEFAULT 0 | |
| `is_hot_reply` | TINYINT | DEFAULT 0 | |
| `author_fans` | INT | DEFAULT 0 | |
| `author_level` | INT | DEFAULT 0 | |
| `author_post_count` | INT | DEFAULT 0 | |
| `has_image` | TINYINT | DEFAULT 0 | |
| `has_video` | TINYINT | DEFAULT 0 | |
| `board_name` | VARCHAR(50) | | 板块名 |
| `hot_raw` | DOUBLE | | 原始热度 (加权和) |
| `hot_norm` | DOUBLE | | 归一化热度 (0-1) |
| `hot_score` | DOUBLE | | 最终热度 |
| `text_length` | INT | DEFAULT 0 | 文本长度 |
| `sentiment_score` | FLOAT | DEFAULT 0 | 情感分数 |
| `created_at` | DATETIME | DEFAULT NOW() | |

**索引：** UNIQUE `(platform, raw_id)`, INDEX `(keyword, publish_time)`, INDEX `(publish_time)`

### 3.2 `content_metrics` — 指标时序表

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | PK |
| `raw_id` | VARCHAR(64) | 关联 standardized_data |
| `platform` | TINYINT | |
| `captured_at` | DATETIME | 回访时间 |
| `comment_count` ~ `view_count` | INT | 各指标当前值 |
| `hot_raw`, `hot_score` | DOUBLE | 当前热度 |
| `lambda` | DOUBLE | 回访调度 lambda |
| `revisit_level` | INT | 回访等级 |

### 3.3 `crawl_queue` — 回访队列表

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | PK |
| `raw_id` | VARCHAR(64) | |
| `platform` | TINYINT | |
| `url` | VARCHAR(500) | 原始 URL |
| `keyword` | VARCHAR(100) | |
| `first_captured` | DATETIME | 首次爬取时间 |
| `last_visited` | DATETIME | 上次回访 |
| `next_visit` | DATETIME | 计划下次回访 |
| `current_lambda` | DOUBLE | 衰减率 |
| `revisit_level` | INT | 0=首次, 1=热门, 2=热点, 3=中等, 4=低频, -1=死链 |
| `status` | VARCHAR(16) | active/paused/dead |
| `visit_count` | INT | 总回访次数 |

### 3.4 `author_stats` — 作者统计表

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | PK |
| `author` | VARCHAR(128) | NOT NULL |
| `platform` | TINYINT | |
| `avg_hot` | DOUBLE | 平均热度 |
| `avg_like` | DOUBLE | 平均点赞 |
| `avg_comment` | DOUBLE | 平均评论 |
| `post_count` | INT | 发帖数 |
| `last_updated` | DATETIME | |
| `created_at` | DATETIME | |

---

## 4. REST API (Spring Boot)

Base URL: `http://<HOST>:8080`

所有响应包裹在统一格式中：

```json
{ "code": 200, "message": "success", "data": <T> }
```

### 4.1 接口列表

| Method | Path | 参数 | data 类型 | 说明 |
|--------|------|------|-----------|------|
| GET | `/api/opinion/metrics` | keyword, timeRange | `MetricDTO` | 概览指标 |
| GET | `/api/opinion/channel` | keyword, timeRange | `List<ChannelDTO>` | 渠道分布 |
| GET | `/api/opinion/channel-trend` | keyword, timeRange | `List<ChannelTrendDTO>` | 渠道趋势 |
| GET | `/api/opinion/trend` | keyword, timeRange | `List<TrendDTO>` | 热度趋势 (12 窗口) |
| GET | `/api/opinion/words` | keyword, timeRange | `List<WordDTO>` | 词云 (top120) |
| GET | `/api/opinion/sentiment-words` | keyword, timeRange | `SentimentWordGroupDTO` | 情感词分组 |
| GET | `/api/opinion/sentiment-timeline` | keyword, timeRange | `List<SentimentTimelineDTO>` | 情感时间线 |
| GET | `/api/opinion/list` | keyword, timeRange | `List<InfoItemDTO>` | 信息流 (top6) |
| GET | `/api/opinion/warnings` | timeRange | `List<WarningDTO>` | 预警面板 |
| GET | `/api/opinion/authors` | keyword, timeRange | `List<AuthorDTO>` | 作者排行 |
| GET | `/api/opinion/keywords` | — | `List<String>` | 全部关键词 |
| GET | `/api/opinion/data-count` | — | `DataCountDTO` | 数据统计 |
| GET | `/api/predict/trend` | keyword | `PredictDTO` | 趋势预测 |
| POST | `/api/predict/trend/batch` | `{"keywords": [...]}` | `List<PredictDTO>` | 批量预测 |

### 4.2 DTO 结构

**MetricDTO:**
```json
{
  "averageHotIndex": 45.2,
  "hotIndexChange": 3.8,
  "sentimentRatio": { "positive": 45, "neutral": 30, "negative": 25 },
  "socialMediaRatio": 75,
  "traditionalMediaRatio": 25,
  "trendData": [40, 42, 44, 46, 45, 47]
}
```

**ChannelDTO:**
```json
{ "channel": "B站", "value": 65 }
```

**ChannelTrendDTO:**
```json
{ "date": "03/20 14:00", "bilibiliValue": 320.5, "ngaValue": 180.2, "ngaRatio": 36.0 }
```

**TrendDTO:**
```json
{
  "date": "03/20 14:00",
  "value": 280,
  "topContents": [
    { "title": "一个热门帖子", "platform": "B站", "hotValue": 85.3, "contributionRatio": 30.5 }
  ]
}
```

**WordDTO:**
```json
{ "word": "原神", "weight": 95, "sentimentScore": 0.72, "hotTitle": "...", "hotPlatform": "B站", "hotValue": 82.1 }
```

**SentimentWordGroupDTO:**
```json
{
  "sentiment": "positive",
  "label": "正面",
  "words": [{ "word": "好玩", "weight": 80, "count": 120 }]
}
```

**SentimentTimelineDTO:**
```json
{ "date": "03/20 14:00", "positive": 45, "neutral": 30, "negative": 25 }
```

**InfoItemDTO:**
```json
{
  "id": 1,
  "title": "帖子标题",
  "source": "B站",
  "time": "3小时前",
  "sentiment": "positive",
  "hotValue": 2500,
  "hotChange": 150,
  "hotChangePercent": 6.4,
  "trend": "up"
}
```

**WarningDTO:**
```json
{
  "keyword": "原神",
  "currentHot": 82.5,
  "changeRate": 15.3,
  "trend": "增长",
  "trendCode": 3,
  "confidence": 0.85,
  "level": "warning",
  "message": "原神热度异常上升，建议关注"
}
```

**AuthorDTO:**
```json
{ "author": "知名UP主", "contentCount": 15, "totalHot": 12500.0, "avgHot": 833.3 }
```

**PredictDTO:**
```json
{
  "keyword": "原神",
  "trend_code": 3,
  "trend_label": "涨",
  "confidence": 0.82,
  "predicted_hot": 95.5,
  "current_hot": 82.3,
  "change_rate": 16.0,
  "strategy": "同日同比·均值回归",
  "message": ""
}
```

---

## 5. 数据流总览

```
爬虫 (Python)
  │  产出: Kafka JSON 消息 (见 §1)
  ▼
Kafka (3 brokers)
  │  Topic: crawler_data, bilibili_video, bilibili_comment
  ▼
Spark Streaming (Scala)
  │  清洗: HTML去除 → 文本归一化 → 热度计算 → 情感调用
  │  产出: 标准化 DataFrame (见 §2)
  ▼
MariaDB
  │  表: standardized_data, content_metrics, crawl_queue, author_stats (见 §3)
  ▼
Spring Boot (Java 11)
  │  REST API (见 §4)
  ▼
Vue 3 大屏
```
