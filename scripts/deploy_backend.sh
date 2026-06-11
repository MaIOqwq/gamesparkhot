#!/bin/bash
set -e
cd /opt/opinion-analysis

echo "=== Stopping old backend ==="
kill $(cat app.pid 2>/dev/null) 2>/dev/null || true
sleep 2

echo "=== Backup and replace JAR ==="
cp app.jar app.jar.bak.old 2>/dev/null || true
mv app.jar.new app.jar

echo "=== Starting new backend ==="
nohup java -jar app.jar > app.log 2>&1 &
echo $! > app.pid
sleep 5

echo "=== Checking status ==="
ps aux | grep 'java.*app.jar' | grep -v grep
echo ""
echo "=== Recent log ==="
tail -5 app.log
echo ""
echo "=== Health check ==="
curl -s http://localhost:8080/actuator/health 2>&1 || curl -s http://localhost:8080/api/opinion/metrics?keyword=手机游戏 2>&1 | head -c 200
