#!/bin/bash
# Fix time decay on 233 - add e^{-t/24} to hot_score
# Then rebuild and restart Spark job

set -e

echo "=== Step 1: Back up original ==="
ssh -i <SSH_KEY_PATH> root@<INTRANET_IP> "cp /home/<USER>/deploy_files/src/main/scala/com/example/cleaner/UnifiedDataCleaner.scala /home/<USER>/deploy_files/src/main/scala/com/example/cleaner/UnifiedDataCleaner.scala.bak"

echo "=== Step 2: Apply time decay fix ==="
ssh -i <SSH_KEY_PATH> root@<INTRANET_IP> "sed -i 's/).withColumn(\"hot_score\", col(\"hot_norm\"))/).withColumn(\"hot_score\", col(\"hot_norm\") * exp(lit(-1.0) * (unix_timestamp() - unix_timestamp(col(\"publish_time\"))) \/ lit(86400.0)))/' /home/<USER>/deploy_files/src/main/scala/com/example/cleaner/UnifiedDataCleaner.scala"

echo "=== Step 3: Verify change ==="
ssh -i <SSH_KEY_PATH> root@<INTRANET_IP> "grep -n 'hot_score' /home/<USER>/deploy_files/src/main/scala/com/example/cleaner/UnifiedDataCleaner.scala | head -5"

echo "=== Step 4: Rebuild jar ==="
ssh -i <SSH_KEY_PATH> root@<INTRANET_IP> "cd /home/<USER>/deploy_files && mvn clean package -DskipTests -q 2>&1 | tail -10"

echo "=== Step 5: Kill old Spark job ==="
ssh -i <SSH_KEY_PATH> root@<INTRANET_IP> "pkill -f UnifiedDataCleaner 2>/dev/null; sleep 3; echo 'Killed'"

echo "=== Step 6: Restart Spark job ==="
ssh -i <SSH_KEY_PATH> root@<INTRANET_IP> "cd /home/<USER>/deploy_files && nohup spark-submit --master local[*] --class com.example.cleaner.UnifiedDataCleaner --driver-memory 1g --executor-memory 1g --conf spark.sql.adaptive.enabled=true --conf spark.sql.adaptive.coalescePartitions.enabled=true --conf spark.streaming.kafka.maxRatePerPartition=1000 target/spark-data-cleaner-1.0-SNAPSHOT-jar-with-dependencies.jar > unified-cleaner.log 2>&1 & echo 'Restarted PID:' \$!"

echo ""
echo "=== Done ==="
