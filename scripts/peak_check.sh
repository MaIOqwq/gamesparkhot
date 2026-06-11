#!/bin/bash
mysql -uspark -p123456 -h127.0.0.1 standardized_data -e "SELECT DATE(publish_time) as dt, COUNT(*) as cnt FROM standardized_data WHERE publish_time > '2026-01-01' GROUP BY dt ORDER BY cnt DESC LIMIT 10;"
