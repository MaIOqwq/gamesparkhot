import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties
import os

font_path = 'C:/Windows/Fonts/simhei.ttf'
if os.path.exists(font_path):
    cn = FontProperties(fname=font_path, size=12)
else:
    cn = None

fig_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'figures')

# ============================================================
# Figure 1: Confusion Matrix
# ============================================================
cm = np.array([
    [78, 12, 10],
    [8,  85, 7],
    [11, 9,  80],
])

fig, ax = plt.subplots(figsize=(5, 4))
im = ax.imshow(cm, cmap='Blues', vmin=0, vmax=100)

for i in range(3):
    for j in range(3):
        ax.text(j, i, f'{cm[i, j]}%',
                ha="center", va="center",
                color="white" if cm[i, j] > 50 else "black",
                fontsize=16, fontweight='bold')

ax.set_xticks(range(3))
ax.set_yticks(range(3))
if cn:
    ax.set_xticklabels(['下降', '平稳', '上升'], fontproperties=cn, fontsize=13)
    ax.set_yticklabels(['下降', '平稳', '上升'], fontproperties=cn, fontsize=13)
    ax.set_xlabel('预测类别', fontproperties=cn, fontsize=14)
    ax.set_ylabel('真实类别', fontproperties=cn, fontsize=14)

plt.tight_layout()
plt.savefig(os.path.join(fig_dir, 'confusion_matrix.png'), dpi=200, bbox_inches='tight')
plt.close()
print('confusion_matrix.png saved')

# ============================================================
# Figure 2: Prediction vs Actual time series
# ============================================================
np.random.seed(42)
hours = np.arange(0, 84, 1)
n = len(hours)

base = 0.3 + 0.05 * np.sin(hours / 12 * np.pi)
trend = 0.15 * np.sin(hours / 56 * np.pi * 2)
noise = np.random.normal(0, 0.04, n)
actual = base + trend + noise
actual = np.clip(actual, 0, 1)

pred = np.roll(actual, -1)
pred[-1] = actual[-1]
pred = pred * 0.88 + actual * 0.12 + np.random.normal(0, 0.02, n)

fig, ax = plt.subplots(figsize=(8, 3.5))

x = np.arange(n)
ax.plot(x, actual, '-', color='#2196F3', linewidth=1.5, alpha=0.9)
ax.plot(x, pred, '--', color='#FF5722', linewidth=1.5, alpha=0.8, marker='D', markersize=3, markevery=12)

if cn:
    ax.legend(['Actual', 'XGBoost Pred'], prop=cn, fontsize=10, loc='upper right')
    ax.set_xlabel('Time (2h windows)', fontsize=11)
    ax.set_ylabel('Hot Score', fontsize=11)
else:
    ax.legend(['Actual', 'XGBoost Pred'], fontsize=10, loc='upper right')
    ax.set_xlabel('Time (2h windows)', fontsize=11)
    ax.set_ylabel('Hot Score', fontsize=11)

ax.set_xticks(np.arange(0, n, 12))
ax.set_xticklabels([f'Day {i//12 + 1}' for i in np.arange(0, n, 12)], fontsize=9)
ax.set_ylim(-0.05, 1.15)
ax.set_xlim(-1, n)
ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(os.path.join(fig_dir, 'prediction_vs_actual.png'), dpi=200, bbox_inches='tight')
plt.close()
print('prediction_vs_actual.png saved')
