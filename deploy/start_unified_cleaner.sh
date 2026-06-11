#!/bin/bash

# 缁熶竴鏁版嵁娓呮礂鍚姩鑴氭湰

echo "=== 缁熶竴鏁版嵁娓呮礂鍚姩鑴氭湰 ==="

# 璁剧疆宸ヤ綔鐩綍
SPARK_HOME="/home/username/spark"
PROJECT_DIR="$SPARK_HOME"
JAR_PATH="$PROJECT_DIR/target/spark-data-cleaner-1.0-SNAPSHOT-jar-with-dependencies.jar"

# 缂栬瘧椤圭洰
echo "1. 缂栬瘧椤圭洰..."
cd "$PROJECT_DIR"
mvn clean package -DskipTests

if [ $? -ne 0 ]; then
    echo "缂栬瘧澶辫触锛?
    exit 1
fi

echo "缂栬瘧鎴愬姛锛?

# 鍒涘缓Kafka涓婚锛堝鏋滀笉瀛樺湪锛?echo "2. 妫€鏌afka涓婚..."
kafka-topics.sh --bootstrap-server <INTRANET_IP>:9092 --list | grep -q "crawler_data"
if [ $? -ne 0 ]; then
    echo "鍒涘缓Kafka涓婚 crawler_data..."
    kafka-topics.sh --bootstrap-server <INTRANET_IP>:9092 --create --topic crawler_data --partitions 4 --replication-factor 1
fi

# 鍚姩鏁版嵁娓呮礂搴旂敤
echo "3. 鍚姩缁熶竴鏁版嵁娓呮礂搴旂敤..."
nohup spark-submit \
  --master local[*] \
  --class com.example.cleaner.UnifiedDataCleaner \
  --driver-memory 1g \
  --executor-memory 1g \
  --conf spark.sql.adaptive.enabled=true \
  --conf spark.sql.adaptive.coalescePartitions.enabled=true \
  --conf spark.streaming.kafka.maxRatePerPartition=1000 \
  "$JAR_PATH" \
  > unified-cleaner.log 2>&1 &

echo "缁熶竴鏁版嵁娓呮礂搴旂敤宸插惎鍔紒"
echo "杩涚▼ID: $!"
echo "鏃ュ織鏂囦欢: unified-cleaner.log"
echo ""
echo "浣跨敤浠ヤ笅鍛戒护鏌ョ湅鏃ュ織锛?
echo "  tail -f unified-cleaner.log"
echo ""
echo "浣跨敤浠ヤ笅鍛戒护鏌ョ湅杩涚▼锛?
echo "  ps aux | grep UnifiedDataCleaner"
