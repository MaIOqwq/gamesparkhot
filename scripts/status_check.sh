#!/bin/bash
echo "=== Java鍚庣 8080 ==="
ps aux | grep 'java.*app.jar' | grep -v grep | awk '{print "PID:"$2" CPU:"$3" MEM:"$4}'
echo "=== Python棰勬祴 5000 ==="
curl -s http://localhost:5000/health
echo ""
echo "=== MariaDB ==="
systemctl is-active mariadb
echo "=== Redis ==="
redis-cli ping 2>&1
echo ""
echo "=== 233鑺傜偣 Kafka/Spark ==="
ssh -i <SSH_KEY_PATH> root@<INTRANET_IP> 'ps aux | grep -E "kafka|spark|sentiment" | grep -v grep | awk "{print \$11\" PID:\"\$2}"' 2>&1 | head -5
