#!/bin/bash
echo "=== 王者荣耀 prediction ==="
curl -s 'http://localhost:8080/api/predict/trend?keyword=%E7%8E%8B%E8%80%85%E8%8D%A3%E8%80%80' | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('HTTP code:', d.get('code'))
data = d.get('data') or {}
print(f'predicted_hot: {data.get(\"predicted_hot\")}')
print(f'current_hot: {data.get(\"current_hot\")}')
print(f'change_rate: {data.get(\"change_rate\")}')
print(f'trend_label: {data.get(\"trend_label\")}')
"

echo ""
echo "=== Test multiple keywords ==="
for kw in '手机游戏' '王者荣耀' '原神' '和平精英'; do
  encoded=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$kw'))")
  result=$(curl -s "http://localhost:8080/api/predict/trend?keyword=$encoded" | python3 -c "
import sys, json
d = json.load(sys.stdin)
data = d.get('data') or {}
print(f'{data.get(\"predicted_hot\", \"N/A\")}')
" 2>/dev/null)
  echo "  $kw: predicted_hot=$result"
done
