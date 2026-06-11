#!/bin/bash
# Test 7d time range
echo "=== 7天 ==="
curl -s 'http://localhost:8080/api/opinion/authors?keyword=%E7%8E%8B%E8%80%85%E8%8D%A3%E8%80%80&timeRange=7d' | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('Code:', d.get('code'))
for a in (d.get('data') or [])[:5]:
    print(f'  {a[\"author\"]}: {a[\"contentCount\"]}条, 总{a[\"totalHot\"]}, 均{a[\"avgHot\"]}')
"

echo ""
echo "=== 全部 ==="
curl -s 'http://localhost:8080/api/opinion/authors?keyword=%E7%8E%8B%E8%80%85%E8%8D%A3%E8%80%80&timeRange=all' | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('Code:', d.get('code'))
for a in (d.get('data') or [])[:5]:
    print(f'  {a[\"author\"]}: {a[\"contentCount\"]}条, 总{a[\"totalHot\"]}, 均{a[\"avgHot\"]}')
"
