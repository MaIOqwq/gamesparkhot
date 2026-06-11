#!/bin/bash

# 统一数据清洗启动脚本

echo "=== 统一数据清洗启动脚本 ==="

# 设置工作目录
SPARK_HOME="${SPARK_HOME:-/opt/spark}"
PROJECT_DIR="$SPARK_HOME"
JAR_PATH="$PROJECT_DIR/target/spark-data-cleaner-1.0-SNAPSHOT-jar-with-dependencies.jar"

# 编译项目
echo "1. 编译项目..."
cd "$PROJECT_DIR"
mvn clean package -DskipTests

if [ $? -ne 0 ]; then
    echo "编译失败！"
    exit 1
fi

echo "编译成功！"

# 创建Kafka主题（如果不存在）
echo "2. 检查Kafka主题..."
kafka-topics.sh --bootstrap-server ${KAFKA_BOOTSTRAP_SERVERS} --list | grep -q "crawler_data"
if [ $? -ne 0 ]; then
    echo "创建Kafka主题 crawler_data..."
    kafka-topics.sh --bootstrap-server ${KAFKA_BOOTSTRAP_SERVERS} --create --topic crawler_data --partitions 4 --replication-factor 1
fi

# 启动数据清洗应用
echo "3. 启动统一数据清洗应用..."
nohup spark-submit \
  --master local[*] \
  --class com.example.cleaner.UnifiedDataCleaner \
  --driver-memory 1g \
  --executor-memory 1.5g \
  --conf spark.sql.adaptive.enabled=true \
  --conf spark.sql.adaptive.coalescePartitions.enabled=true \
  --conf spark.streaming.kafka.maxRatePerPartition=1000 \
  "$JAR_PATH" \
  > unified-cleaner.log 2>&1 &

echo "统一数据清洗应用已启动！"
echo "进程ID: $!"
echo "日志文件: unified-cleaner.log"
echo ""
echo "使用以下命令查看日志："
echo "  tail -f unified-cleaner.log"
echo ""
echo "使用以下命令查看进程："
echo "  ps aux | grep UnifiedDataCleaner"
