#!/bin/bash
echo "=== Backfill time decay for existing records ==="
mysql -uspark -p123456 standardized_data -e "UPDATE standardized_data SET hot_score = ROUND(hot_norm * EXP(-1.0 * GREATEST(TIMESTAMPDIFF(HOUR, publish_time, NOW()), 0) / 24.0), 4) WHERE hot_norm > 0 AND ABS(hot_score - hot_norm) < 0.0001;"

echo ""
echo "=== Verify after backfill ==="
mysql -uspark -p123456 standardized_data -e "SELECT COUNT(*) as total, SUM(CASE WHEN hot_score < hot_norm THEN 1 ELSE 0 END) as decayed, SUM(CASE WHEN ABS(hot_score - hot_norm) < 0.0001 THEN 1 ELSE 0 END) as unchanged FROM standardized_data WHERE hot_norm > 0.01;"

echo ""
echo "=== Sample decayed records ==="
mysql -uspark -p123456 standardized_data -e "SELECT raw_id, ROUND(hot_norm,4) as hot_norm, ROUND(hot_score,4) as hot_score, publish_time, TIMESTAMPDIFF(HOUR, publish_time, NOW()) as hours_ago FROM standardized_data WHERE hot_norm > 0.5 ORDER BY publish_time DESC LIMIT 8;"
