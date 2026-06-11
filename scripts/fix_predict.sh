#!/bin/bash
# Fix predict_service.py: compute real predicted_hot instead of copying current_hot
set -e

cd /opt/opinion-analysis/predict

echo "=== Backing up ==="
cp predict_service.py predict_service.py.bak

echo "=== Patching predicted_hot calculation ==="

python3 << 'PYFIX'
import re

with open('predict_service.py', 'r') as f:
    content = f.read()

# Find the result dict construction and replace predicted_hot line
old = "'predicted_hot': current_hot,"
new = """'predicted_hot': round(
        current_hot * (1.0 + (prob_dict.get('上升', 0.0) - prob_dict.get('下降', 0.0))
                       * max(abs(float(feat['total_hot_change_rate'])), 0.05))
    ),"""

if old in content:
    content = content.replace(old, new, 1)
    with open('predict_service.py', 'w') as f:
        f.write(content)
    print("PATCHED: predicted_hot now uses probability-weighted estimate")
else:
    print("WARNING: old pattern not found, checking...")
    # Try alternate pattern
    if 'predicted_hot' in content:
        for i, line in enumerate(content.split('\n')):
            if 'predicted_hot' in line:
                print(f"  Line {i+1}: {line.strip()}")
    exit(1)

# Also need to add prob_dict computation BEFORE the result dict
# Insert after prob = float(max(proba))
old_prob = "    prob = float(max(proba))"
prob_dict_code = """
    # Build probability map for each class
    prob_dict = {}
    for i in range(len(proba)):
        label = class_map.get(i, '平稳')
        prob_dict[label] = float(proba[i])"""

if old_prob in content:
    content = content.replace(old_prob, old_prob + prob_dict_code, 1)
    with open('predict_service.py', 'w') as f:
        f.write(content)
    print("PATCHED: added prob_dict computation")
else:
    print("WARNING: prob line not found")
    exit(1)

print("All patches applied successfully")
PYFIX

echo "=== Verifying ==="
grep -n 'predicted_hot\|prob_dict' predict_service.py | head -10

echo "=== Restarting predict service ==="
kill $(ps aux | grep 'predict_service.py' | grep -v grep | awk '{print $2}') 2>/dev/null || true
sleep 2
nohup ./venv/bin/python predict_service.py > predict.log 2>&1 &
sleep 3
curl -s http://localhost:5000/health

echo ""
echo "=== Testing prediction ==="
curl -s 'http://localhost:5000/api/predict/trend?keyword=%E6%89%8B%E6%9C%BA%E6%B8%B8%E6%88%8F' | python3 -m json.tool 2>/dev/null || curl -s 'http://localhost:5000/api/predict/trend?keyword=%E6%89%8B%E6%9C%BA%E6%B8%B8%E6%88%8F'

echo ""
echo "=== Done ==="
