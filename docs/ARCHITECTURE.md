# 系统架构概述

## 1. 总体架构

GameOpinion 采用分层架构，从数据采集到可视化展示共 6 层：

```
┌─────────────────────────────────────────────┐
│            可视化层 (Vue 3 大屏)               │
│  ECharts 图表 · 预警面板 · 词云 · 排行榜       │
└──────────────────┬──────────────────────────┘
                   │ HTTP REST API
┌──────────────────▼──────────────────────────┐
│             后端服务层 (Spring Boot)           │
│    OpinionController · PredictController     │
│    OpinionService · CacheService (Redis)     │
└──────────────────┬──────────────────────────┘
                   │ JDBC
┌──────────────────▼──────────────────────────┐
│             数据存储层 (MariaDB)               │
│  standardized_data · content_metrics         │
│  crawl_queue · author_stats                  │
└──────────────────┬──────────────────────────┘
                   │ JDBC / Spark
┌──────────────────▼──────────────────────────┐
│           流处理层 (Spark Streaming)          │
│  BiliDataCleaner · NgaDataCleaner           │
│  UnifiedDataCleaner · 数据归一化              │
└──────────────────┬──────────────────────────┘
                   │ Kafka Consumer
┌──────────────────▼──────────────────────────┐
│           消息队列层 (Kafka)                  │
│  crawler_data · bilibili_video/comment      │
│  nga_context/comment                        │
└──────────────────┬──────────────────────────┘
                   │ Produce
┌──────────────────▼──────────────────────────┐
│            数据采集层 (爬虫)                   │
│  B站/抖音/微博/小红书/知乎/贴吧/快手/NGA      │
└─────────────────────────────────────────────┘
```

## 2. 核心模块

### 2.1 爬虫模块

- **B站爬虫**: 基于 MediaCrawler 二次开发，Playwright 自动化 + API 混合
- **NGA 爬虫**: Playwright 获取 Cookie + cloudscraper/httpx 爬取帖子内容
- **支持平台**: Bilibili, Douyin, Weibo, Xiaohongshu (小红书), Zhihu, Tieba, Kuaishou, NGA
- **数据格式**: JSONL → Kafka Producer

### 2.2 流处理模块 (Spark)

- **语言**: Scala 2.12, Spark 3.3
- **作业类型**:
  - `UnifiedDataCleaner`: 统一清洗入口，消费 `crawler_data` 主题
  - `BiliDataCleaner`: B站数据专用清洗
  - `NgaDataCleaner`: NGA 数据专用清洗
  - `BatchDataCleaner`: 离线批量清洗
- **清洗逻辑**: HTML 标签去除、特殊字符过滤、文本归一化、热度计算（加权和 + 衰减因子）
- **窗口**: 5 秒微批次 Streaming

### 2.3 后端模块 (Spring Boot)

- **Controller 层**: REST API，支持按关键词和时间范围查询
- **Service 层**: 指标聚合、趋势计算、情感统计、词云生成、预警检测
- **Repository 层**: Spring Data JPA，复杂 SQL 通过 `@Query` 实现
- **缓存**: Redis 缓存热点查询结果，减少数据库压力
- **分词**: Ansj 分词库处理中文文本

### 2.4 前端模块 (Vue 3)

- **技术栈**: Vue 3 (Composition API) + TypeScript + Vite + Tailwind CSS
- **大屏组件**:
  - MetricCard: 概览指标卡（总帖子数、参与作者数、总互动数）
  - ChannelChart: 平台渠道分布图（饼图）
  - TrendChart: 趋势折线图（含预测值）
  - WordCloudSim: 词云
  - InfoList: 热门内容列表
  - WarningPanel: 预警面板（异常检测）
  - SentimentTopicsCard: 情感主题分布
  - AuthorRanking: 作者贡献排行

### 2.5 预测模块 (ML)

- **情感分析**: PaddleNLP ERNIE / SKEP 模型
- **热度分类**: XGBoost 多分类（3类/5类）预测热度等级
- **趋势回归**: XGBoost 回归 + LSTM 预测具体热度值
- **训练周期**: 2小时 / 12小时 / 24小时预测窗口

## 3. 数据流

```
爬虫采集 → Kafka → Spark Streaming 清洗 → MariaDB
                                              ↓
                                       Spring Boot API
                                              ↓
                                    Vue 3 Dashboard ← ML 预测 ← 训练脚本
```

## 4. 关键技术决策

- **为什么用 Kafka?** 解耦爬虫和数据处理，支持多消费者、数据回放、削峰填谷
- **为什么用 Spark Streaming?** 相比 Flink 学习成本更低，与现有 Scala 技术栈一致，适合 5 秒级别的微批次处理
- **为什么用 MariaDB 而不是 MySQL?** MariaDB 与 MySQL 完全兼容，性能更好，社区更活跃
- **为什么爬虫混合 Playwright + httpx?** NGA 反爬严格，Playwright 获取真实 Cookie 后转 httpx 提高效率
