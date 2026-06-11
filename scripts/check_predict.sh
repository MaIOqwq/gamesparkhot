#!/bin/bash
echo "=== Python predict 5000 ==="
curl -s 'http://localhost:5000/api/predict/trend?keyword=%E7%8E%8B%E8%80%85%E8%8D%A3%E8%80%80' | python3 -c "
import sys, json
d = json.load(sys.stdin)
data = d.get('data', {})
print('predicted_hot:', data.get('predicted_hot'))
print('current_hot:', data.get('current_hot'))
print('change_rate:', data.get('change_rate'))
print('trend_label:', data.get('trend_label'))
"

echo ""
echo "=== Java /api/predict/trend (8080) ==="
curl -s 'http://localhost:8080/api/predict/trend?keyword=%E7%8E%8B%E8%80%85%E8%8D%A3%E8%80%80' | python3 -c "
import sys, json
d = json.load(sys.stdin)
data = d.get('data', {})
print('predicted_hot:', data.get('predicted_hot'))
print('current_hot:', data.get('current_hot'))
print('change_rate:', data.get('change_rate'))
print('strategy:', data.get('strategy'))
"

echo ""
echo "=== Java /api/opinion/trend (last 6 entries) ==="
curl -s 'http://localhost:8080/api/opinion/trend?keyword=%E7%8E%8B%E8%80%85%E8%8D%A3%E8%80%80&timeRange=7d' | python3 -c "
import sys, json
d = json.load(sys.stdin)
items = d.get('data', [])
for x in items[-6:]:
    print(x.get('date',''), 'predicted:', x.get('predictedHot','N/A'), 'current:', x.get('hotIndex','N/A'))
"
