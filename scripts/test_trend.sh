#!/bin/bash
echo "=== Trend data (last 3 points) ==="
curl -s 'http://localhost:8080/api/opinion/trend?keyword=%E6%89%8B%E6%9C%BA%E6%B8%B8%E6%88%8F&timeRange=1d' | python3 -c "
import sys, json
d = json.load(sys.stdin)
td = d.get('data', [])
print(f'Total points: {len(td)}')
for p in td[-3:]:
    print(f'  {p[\"date\"]}: {p[\"value\"]}')
"

echo ""
echo "=== Predict API ==="
curl -s 'http://localhost:8080/api/predict/trend?keyword=%E6%89%8B%E6%9C%BA%E6%B8%B8%E6%88%8F' | python3 -m json.tool

echo ""
echo "=== Test with active keyword ==="
curl -s 'http://localhost:5000/api/predict/trend?keyword=%E7%8E%8B%E8%80%85%E8%8D%A3%E8%80%80' | python3 -m json.tool
