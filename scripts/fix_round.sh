#!/bin/bash
cd /opt/opinion-analysis/predict

# Fix: replace round(...) with round(..., 2) in predicted_hot
python3 << 'PYFIX'
with open('predict_service.py', 'r') as f:
    content = f.read()

# The predicted_hot line has round(...) — need to change to round(..., 2)
# Find: round(\n        current_hot * ...
old = """'predicted_hot': round(
        current_hot * (1.0 + (prob_dict.get('上升', 0.0) - prob_dict.get('下降', 0.0))
                       * max(abs(float(feat['total_hot_change_rate'])), 0.05))
    ),"""

new = """'predicted_hot': round(
        current_hot * (1.0 + (prob_dict.get('上升', 0.0) - prob_dict.get('下降', 0.0))
                       * max(abs(float(feat['total_hot_change_rate'])), 0.05)),
        2
    ),"""

if old in content:
    content = content.replace(old, new, 1)
    with open('predict_service.py', 'w') as f:
        f.write(content)
    print("PATCHED: round() -> round(..., 2)")
else:
    print("WARNING: pattern not found")
    # Show the current predicted_hot lines
    for i, line in enumerate(content.split('\n')):
        if 'predicted_hot' in line:
            print(f"  {i+1}: {line.strip()}")

print("Done")
PYFIX

# Restart service
kill $(ps aux | grep 'predict_service.py' | grep -v grep | awk '{print $2}') 2>/dev/null || true
sleep 2
nohup ./venv/bin/python predict_service.py > predict.log 2>&1 &
sleep 3

# Test
echo "=== Test 手机游戏 ==="
curl -s 'http://localhost:5000/api/predict/trend?keyword=%E6%89%8B%E6%9C%BA%E6%B8%B8%E6%88%8F' | python3 -m json.tool
echo ""
echo "=== Test 王者荣耀 ==="
curl -s 'http://localhost:5000/api/predict/trend?keyword=%E7%8E%8B%E8%80%85%E8%8D%A3%E8%80%80' | python3 -m json.tool
