"""
LSTM + Attention 鈥?姣忎釜鍏抽敭璇嶇嫭绔嬮娴?hot_raw 鍙樺寲閲?(delta)
"""
import json, warnings
import numpy as np
import pandas as pd
import pymysql
from datetime import datetime
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset

warnings.filterwarnings('ignore')
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"[{datetime.now():%H:%M:%S}] device={device}")

# 鍙傛暟
SEQ_LEN = 8           # 杩囧幓 8 涓獥鍙ｏ紙2 澶╋級锛岄娴嬪彉鍖栭噺涓嶉渶瑕佸お闀跨殑鍘嗗彶
BATCH_SIZE = 64
HIDDEN_SIZE = 64
NUM_LAYERS = 2
EPOCHS = 100
LR = 1e-3

print("杩炴帴鏁版嵁搴?..")
conn = pymysql.connect(host='<SERVER_IP>', port=3306, user='spark',
                       password = <DB_PASSWORD>, database='standardized_data', charset='utf8mb4')
df = pd.read_sql("SELECT * FROM standardized_data WHERE publish_time >= '2023-01-01' ORDER BY keyword, publish_time", conn)
conn.close()
print(f"鍏?{len(df)} 鏉¤褰?)

# 鑱氬悎鍒?6h 绐楀彛
df['publish_time'] = pd.to_datetime(df['publish_time'])
df['window_start'] = df['publish_time'].dt.floor('6H')

agg = df.groupby(['keyword', 'window_start']).agg(
    total_hot=('hot_raw', 'sum'),
    count=('id', 'count'),
    avg_sentiment=('sentiment_score', 'mean'),
    total_like=('like_count', 'sum'),
    total_comment=('comment_count', 'sum'),
).reset_index().sort_values(['keyword', 'window_start'])

# 棰濆鐗瑰緛
agg['log_hot'] = np.log1p(agg['total_hot'])
agg['log_count'] = np.log1p(agg['count'])
agg['hour'] = agg['window_start'].dt.hour
agg['day_of_week'] = agg['window_start'].dt.dayofweek

# Target: 涓嬩竴绐楀彛鐨?log_hot 鍙樺寲閲?(delta = next - current)
# 棰勬祴鍙樺寲閲忔瘮棰勬祴缁濆鍊兼洿绋冲畾锛岄伩鍏嶆ā鍨嬪彧瀛︿範杈撳嚭鍧囧€?agg['target'] = agg.groupby('keyword')['log_hot'].transform(lambda x: x.shift(-1) - x)

# 鐗瑰緛
agg['delta_lag1'] = agg.groupby('keyword')['log_hot'].diff().fillna(0)  # 涓婁竴绐楀彛鐨勫彉鍖栭噺锛堝姩閲忎俊鍙凤級锛岄琛屽～0
FEATURES = ['log_hot', 'log_count', 'avg_sentiment', 'hour', 'day_of_week',
            'total_like', 'total_comment', 'delta_lag1']
TARGET = 'target'

agg = agg.dropna(subset=[TARGET]).reset_index(drop=True)
print(f"鏈夋晥绐楀彛鏁? {len(agg)}")

# ========= 妯″瀷 =========
class Attention(nn.Module):
    def __init__(self, hidden_size):
        super().__init__()
        self.attn = nn.Linear(hidden_size, 1)
    def forward(self, lstm_out):
        # lstm_out: (batch, seq_len, hidden)
        weights = torch.softmax(self.attn(lstm_out).squeeze(-1), dim=1)
        return torch.sum(lstm_out * weights.unsqueeze(-1), dim=1)

class LSTMAttention(nn.Module):
    def __init__(self, input_size, hidden_size, num_layers):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=0.2)
        self.attn = Attention(hidden_size)
        self.fc = nn.Linear(hidden_size, 1)
    def forward(self, x):
        lstm_out, _ = self.lstm(x)
        context = self.attn(lstm_out)
        return self.fc(context).squeeze(-1)

# ========= 璁粌鍑芥暟 =========
def train_keyword(kw, data):
    """璁粌鍗曚釜鍏抽敭璇嶇殑 LSTM+Attention"""
    kw_data = data[data['keyword'] == kw].sort_values('window_start').reset_index(drop=True)
    if len(kw_data) < SEQ_LEN + 50:
        return None, 0, 0, 0, 0

    # 鎸夋椂闂村垝鍒?    train = kw_data[kw_data['window_start'] < '2026-01-01']
    test = kw_data[kw_data['window_start'] >= '2026-01-01']
    if len(train) < SEQ_LEN + 10 or len(test) < 10:
        return None, 0, 0, 0, 0

    # 褰掍竴鍖?    feat_mean = train[FEATURES].mean()
    feat_std = train[FEATURES].std().clip(1e-6)
    target_mean = train[TARGET].mean()
    target_std = train[TARGET].std().clip(1e-6)

    def make_sequences(data):
        X, y = [], []
        vals = (data[FEATURES].values - feat_mean.values) / feat_std.values
        tgt = (data[TARGET].values - target_mean) / target_std
        for i in range(len(data) - SEQ_LEN):
            X.append(vals[i:i+SEQ_LEN])
            y.append(tgt[i+SEQ_LEN])
        return torch.FloatTensor(np.array(X)), torch.FloatTensor(np.array(y))

    X_train, y_train = make_sequences(train)
    X_test, y_test = make_sequences(test)

    if len(X_train) < 10:
        return None, 0, 0, 0, 0

    loader = DataLoader(TensorDataset(X_train, y_train), batch_size=BATCH_SIZE, shuffle=True)

    model = LSTMAttention(len(FEATURES), HIDDEN_SIZE, NUM_LAYERS).to(device)
    optimizer = optim.Adam(model.parameters(), lr=LR)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)
    loss_fn = nn.MSELoss()

    best_loss = float('inf')
    best_state = None
    for epoch in range(EPOCHS):
        model.train()
        total_loss = 0
        for Xb, yb in loader:
            Xb, yb = Xb.to(device), yb.to(device)
            optimizer.zero_grad()
            loss = loss_fn(model(Xb), yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item()

        model.eval()
        with torch.no_grad():
            val_loss = loss_fn(model(X_test.to(device)), y_test.to(device)).item()
        scheduler.step(val_loss)

        if val_loss < best_loss:
            best_loss = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

        if epoch % 20 == 0:
            print(f"    [{kw[:4]} epoch {epoch:3d}] train_loss={total_loss/len(loader):.4f} val_loss={val_loss:.4f}")

    # 娴嬭瘯璇勪及
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        pred_norm = model(X_test.to(device)).cpu().numpy()
        true_norm = y_test.numpy()

    # 杩樺師 delta 鍒板師濮嬪昂搴?    pred_delta = pred_norm * target_std + target_mean
    true_delta = true_norm * target_std + target_mean

    # 鑾峰彇褰撳墠绐楀彛鐨?log_hot锛屽皢 delta 杩樺師涓虹粷瀵归娴嬪€?    current_log_hot = test['log_hot'].values[SEQ_LEN:]  # 涓?y 瀵归綈

    pred_log_hot = current_log_hot + pred_delta
    true_log_hot = current_log_hot + true_delta

    pred_raw = np.expm1(pred_log_hot)
    true_raw = np.expm1(true_log_hot)

    mae = np.mean(np.abs(pred_raw - true_raw))
    medae = np.median(np.abs(pred_raw - true_raw))
    direction_acc = np.mean((pred_delta > 0) == (true_delta > 0)) * 100

    # 鎸佷箙鍖栧熀绾匡細棰勬祴鍙樺寲閲忎负 0锛堝嵆鐑害涓嶅彉锛?    baseline_raw = np.expm1(current_log_hot)
    baseline_mae = np.mean(np.abs(baseline_raw - true_raw))

    return model, mae, medae, direction_acc, baseline_mae

# ========= 璁粌鎵€鏈夊叧閿瘝 =========
keywords = agg['keyword'].unique()
print(f"\n鍏?{len(keywords)} 涓叧閿瘝锛屽紑濮嬮€愪釜璁粌...\n")

results = []
for kw in keywords:
    print(f"[{datetime.now():%H:%M:%S}] 璁粌 [{kw}]...")
    model, mae, medae, direction_acc, baseline_mae = train_keyword(kw, agg)
    if model:
        improvement = baseline_mae - mae
        print(f"  [OK] [{kw}] MAE={mae:.0f}, MedAE={medae:.0f}, DirAcc={direction_acc:.1f}%, "
              f"鍩虹嚎MAE={baseline_mae:.0f}, 鏀瑰杽={improvement:.0f}")
        results.append({'keyword': kw, 'mae': mae, 'medae': medae,
                        'direction_acc': direction_acc, 'baseline_mae': baseline_mae})
        torch.save(model.state_dict(), f'lstm_{kw}.pt')
    else:
        print(f"  [FAIL] [{kw}] 鏁版嵁涓嶈冻")

print(f"\n{'='*70}")
print(f"{'鍏抽敭璇?:<12} {'MAE':>8} {'MedAE':>8} {'DirAcc':>8} {'鍩虹嚎MAE':>8} {'鏀瑰杽':>8}")
print(f"{'-'*70}")
for r in sorted(results, key=lambda x: x['mae']):
    impr = r['baseline_mae'] - r['mae']
    print(f"  {r['keyword']:<12} {r['mae']:>8.0f} {r['medae']:>8.0f} "
          f"{r['direction_acc']:>7.1f}% {r['baseline_mae']:>8.0f} {impr:>+8.0f}")
if results:
    avg_mae = np.mean([r['mae'] for r in results])
    avg_medae = np.mean([r['medae'] for r in results])
    avg_dir = np.mean([r['direction_acc'] for r in results])
    avg_base = np.mean([r['baseline_mae'] for r in results])
    avg_impr = avg_base - avg_mae
    print(f"{'='*70}")
    print(f"{'骞冲潎':<12} {avg_mae:>8.0f} {avg_medae:>8.0f} {avg_dir:>7.1f}% {avg_base:>8.0f} {avg_impr:>+8.0f}")
    print(f"{'='*70}")
    # 缁熻浼樹簬鍩虹嚎鐨勫叧閿瘝鏁?    better = sum(1 for r in results if r['mae'] < r['baseline_mae'])
    print(f"  浼樹簬鍩虹嚎: {better}/{len(results)} ({better/len(results)*100:.0f}%)")
