#!/bin/bash
echo "=== 字段检查：作者相关 ==="
mysql -uspark -p123456 standardized_data -e "SELECT author, author_fans, author_level, author_post_count, like_count, comment_count, hot_raw, sentiment_score FROM standardized_data WHERE keyword='王者荣耀' AND author IS NOT NULL AND author != '' LIMIT 5;"

echo ""
echo "=== 作者统计 ==="
mysql -uspark -p123456 standardized_data -e "SELECT COUNT(DISTINCT author) as unique_authors, COUNT(*) as total_records FROM standardized_data WHERE keyword='王者荣耀' AND author IS NOT NULL AND author != '';"

echo ""
echo "=== Top 作者 by 粉丝 ==="
mysql -uspark -p123456 standardized_data -e "SELECT author, MAX(author_fans) as fans, MAX(author_level) as level, COUNT(*) as posts, ROUND(AVG(hot_raw),2) as avg_hot FROM standardized_data WHERE keyword='王者荣耀' AND author IS NOT NULL AND author != '' GROUP BY author ORDER BY fans DESC LIMIT 10;"

echo ""
echo "=== 情感 > 0.5 的内容样例 ==="
mysql -uspark -p123456 standardized_data -e "SELECT content_clean, sentiment_score FROM standardized_data WHERE keyword='王者荣耀' AND sentiment_score > 0.8 AND content_clean IS NOT NULL LIMIT 3;" --default-character-set=utf8mb4

echo ""
echo "=== 负面内容样例 ==="
mysql -uspark -p123456 standardized_data -e "SELECT content_clean, sentiment_score FROM standardized_data WHERE keyword='王者荣耀' AND sentiment_score < -0.5 AND content_clean IS NOT NULL LIMIT 3;" --default-character-set=utf8mb4

echo ""
echo "=== 数据总量 ==="
mysql -uspark -p123456 standardized_data -e "SELECT keyword, COUNT(*) as cnt FROM standardized_data WHERE content_clean IS NOT NULL GROUP BY keyword ORDER BY cnt DESC LIMIT 10;"
