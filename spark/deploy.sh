#!/bin/bash

# 部署脚本
# 用于编译和提交Spark作业到云服务

echo "Starting deployment..."

# 设置变量
PROJECT_DIR="$(pwd)"
JAR_NAME="spark-data-cleaner-1.0-SNAPSHOT-jar-with-dependencies.jar"
JAR_PATH="$PROJECT_DIR/target/$JAR_NAME"

# 编译项目
echo "Building project..."
mvn clean package

if [ $? -ne 0 ]; then
    echo "Build failed. Exiting."
    exit 1
fi

echo "Build successful."

# 检查JAR文件是否存在
if [ ! -f "$JAR_PATH" ]; then
    echo "JAR file not found. Exiting."
    exit 1
fi

echo "JAR file created: $JAR_PATH"

# 提交B站数据清洗作业
echo "Submitting BiliDataCleaner job..."
spark-submit \
    --class com.example.cleaner.BiliDataCleaner \
    --master yarn \
    --deploy-mode cluster \
    --executor-memory 2g \
    --executor-cores 2 \
    --driver-memory 1g \
    $JAR_PATH

if [ $? -ne 0 ]; then
    echo "Failed to submit BiliDataCleaner job."
else
    echo "BiliDataCleaner job submitted successfully."
fi

# 提交NGA数据清洗作业
echo "Submitting NgaDataCleaner job..."
spark-submit \
    --class com.example.cleaner.NgaDataCleaner \
    --master yarn \
    --deploy-mode cluster \
    --executor-memory 2g \
    --executor-cores 2 \
    --driver-memory 1g \
    $JAR_PATH

if [ $? -ne 0 ]; then
    echo "Failed to submit NgaDataCleaner job."
else
    echo "NgaDataCleaner job submitted successfully."
fi

echo "Deployment completed."
