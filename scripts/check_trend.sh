#!/bin/bash
echo "=== /api/opinion/trend (fresh, no cache) ==="
curl -s 'http://localhost:8080/api/opinion/trend?keyword=%E7%8E%8B%E8%80%85%E8%8D%A3%E8%80%80&timeRange=7d' | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('code:', d.get('code'))
items = d.get('data', [])
print(f'Total entries: {len(items)}')
for x in items:
    print(f'  {x[\"date\"]:15s} value={x[\"value\"]}')
"

echo ""
echo "=== /api/opinion/trend?timeRange=3d ==="
curl -s 'http://localhost:8080/api/opinion/trend?keyword=%E7%8E%8B%E8%80%85%E8%8D%A3%E8%80%80&timeRange=3d' | python3 -c "
import sys, json
d = json.load(sys.stdin)
items = d.get('data', [])
for x in items:
    print(f'  {x[\"date\"]:15s} value={x[\"value\"]}')
"
