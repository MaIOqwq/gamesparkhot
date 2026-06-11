# 部署指南

## 环境要求

| 组件 | 版本 | 说明 |
|------|------|------|
| Java | 11+ | 后端运行环境 |
| Maven | 3.8+ | 后端和 Spark 项目构建 |
| Apache Spark | 3.3+ | 流处理作业 |
| Kafka | 3.4+ | 消息队列 |
| MariaDB | 10+ | 数据存储 |
| Node.js | 18+ | 前端构建 |
| Python | 3.8+ | 爬虫和 ML 训练 |
| Redis | 6+ | 缓存（可选） |

## 快速部署

### 1. 数据库初始化

```bash
# 创建数据库
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS standardized_data CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 导入表结构
mysql -u root -p standardized_data < spark/sql/create_tables.sql
```

### 2. Kafka 配置

```bash
# 启动 Kafka（假设 Zookeeper 已运行）
cd /path/to/kafka
bin/kafka-server-start.sh config/server.properties

# 创建所需主题
bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --topic crawler_data --partitions 4 --replication-factor 1
bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --topic bilibili_video --partitions 2 --replication-factor 1
bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --topic bilibili_comment --partitions 2 --replication-factor 1
bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --topic nga_context --partitions 2 --replication-factor 1
bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --topic nga_comment --partitions 2 --replication-factor 1
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入实际的服务器地址和密码
```

### 4. 启动爬虫

```bash
cd crawler

# 配置爬虫信息
# 编辑 config.json，填入平台 Cookie 和数据库连接信息

# 启动 NGA 爬虫（示例）
cd nga
pip install -r requirements.txt
python nga_crawler.py

# 启动 B站爬虫
cd ../bilibili/modified
# 按照 MediaCrawler 方式配置和运行
```

### 5. 启动 Spark 流处理作业

```bash
cd spark

# 编译
mvn clean package -DskipTests

# 本地模式运行
spark-submit \
  --master local[*] \
  --class com.example.cleaner.UnifiedDataCleaner \
  --driver-memory 1g \
  --executor-memory 1.5g \
  target/spark-data-cleaner-1.0-SNAPSHOT-jar-with-dependencies.jar
```

### 6. 启动后端

```bash
cd backend

# 编译
mvn clean package -DskipTests

# 运行
java -jar target/opinion-analysis-0.0.1-SNAPSHOT.jar \
  --DB_HOST=localhost \
  --DB_PASSWORD=your_password
```

### 7. 启动前端

```bash
cd frontend
npm install
npm run dev
# 或生产构建
npm run build
# 部署 dist/ 目录到 Nginx
```

### 8. 启动预测服务（可选）

```bash
cd deploy
pip install flask paddlepaddle paddlenlp
python predict_service.py
```

## 生产部署检查清单

- [ ] 修改所有默认密码
- [ ] 配置 Kafka 认证和加密
- [ ] 配置 MariaDB 访问控制和备份
- [ ] 配置 Nginx 反向代理前端
- [ ] 配置 systemd 服务实现自动重启
- [ ] 配置监控和告警
- [ ] 配置日志轮转

## 常见问题

### Q: Kafka 连接失败
A: 检查 `KAFKA_BOOTSTRAP_SERVERS` 环境变量是否正确配置。确认 Kafka 服务已启动且防火墙已开放端口。

### Q: Spark 作业内存不足
A: 在 `spark-submit` 命令中调整 `--executor-memory` 和 `--driver-memory` 参数。

### Q: 数据库连接失败
A: 确认 MariaDB 服务已启动，且用户有远程访问权限：`GRANT ALL ON standardized_data.* TO 'spark'@'%';`

### Q: 爬虫登录失败
A: NGA 和 B站需要有效的 Cookie。使用 Playwright 浏览器自动化获取最新 Cookie。

### Q: 前端跨域问题
A: 后端已配置 CORS，允许 `localhost:5173-5176`。生产环境建议使用 Nginx 反向代理统一域名。
