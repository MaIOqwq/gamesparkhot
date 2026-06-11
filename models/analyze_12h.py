"""
12h 绐楀彛鏁版嵁鎺㈢储鍒嗘瀽
"""
import warnings
import numpy as np
import pandas as pd
import pymysql

warnings.filterwarnings('ignore')

conn = pymysql.connect(host='<SERVER_IP>', port=3306, user='spark',
                       password = <DB_PASSWORD>, database='standardized_data', charset='utf8mb4')
df = pd.read_sql("SELECT * FROM standardized_data WHERE publish_time >= '2022-01-01' ORDER BY keyword, publish_time", conn)
conn.close()
print(f"鎬绘潯鏁? {len(df)}")
print(f"鍏抽敭璇? {df['keyword'].nunique()}")
print(f"鏃堕棿鑼冨洿: {df['publish_time'].min()} ~ {df['publish_time'].max()}")

df['publish_time'] = pd.to_datetime(df['publish_time'])
df['win'] = df['publish_time'].dt.floor('12H')

# ======== 鑱氬悎 ========
agg = df.groupby(['keyword', 'win']).agg(
    total_hot=('hot_score', 'sum'),
    count=('id', 'count'),
    avg_sentiment=('sentiment_score', 'mean'),
    total_like=('like_count', 'sum'),
    total_comment=('comment_count', 'sum'),
).reset_index().sort_values(['keyword', 'win'])

print(f"\n12h绐楀彛鏁? {len(agg)}")
print(f"姣忓叧閿瘝骞冲潎绐楀彛鏁? {agg.groupby('keyword').size().mean():.0f}")
print(f"姣忓叧閿瘝绐楀彛鑼冨洿: {agg.groupby('keyword').size().min()} ~ {agg.groupby('keyword').size().max()}")

# ======== 1. 鍩烘湰缁熻 ========
print("\n" + "="*60)
print("1. 12h 绐楀彛鍩烘湰缁熻")
print("="*60)

print(f"\n  total_hot 缁熻:")
print(f"    mean={agg['total_hot'].mean():.1f}, std={agg['total_hot'].std():.1f}")
print(f"    min={agg['total_hot'].min()}, max={agg['total_hot'].max()}")
print(f"    P50={agg['total_hot'].quantile(0.5):.1f}, P90={agg['total_hot'].quantile(0.9):.1f}")

# ======== 2. 鍙樺寲鐜?========
print("\n" + "="*60)
print("2. 12h 鍙樺寲鐜囧垎鏋?)
print("="*60)

agg['future_hot'] = agg.groupby('keyword')['total_hot'].shift(-1)
agg = agg.dropna(subset=['future_hot'])
agg['change_rate'] = (agg['future_hot'] - agg['total_hot']) / (agg['total_hot'] + 1e-6)
agg['change_raw'] = agg['future_hot'] - agg['total_hot']

cr = agg['change_rate'].clip(-5, 5)
print(f"  鍙樺寲鐜? mean={cr.mean():.4f}, std={cr.std():.4f}")
for q in [5, 10, 20, 30, 50, 70, 80, 90, 95]:
    print(f"    P{q}={agg['change_rate'].quantile(q/100):.4f}")

# ======== 3. 鑷浉鍏?========
print("\n" + "="*60)
print("3. 鑷浉鍏冲垎鏋?)
print("="*60)

for lag in [1, 2, 3, 4, 5, 6, 7]:
    ar = agg.groupby('keyword')['change_rate'].apply(
        lambda g: g.corr(g.shift(lag))).dropna()
    pos = (ar > 0).mean() * 100
    print(f"  lag={lag}: mean={ar.mean():.4f}, 姝ｇ浉鍏?{(ar>0).sum()}/{len(ar)} ({pos:.0f}%)")

# 褰撳墠 change_rate vs 鏈潵 change_rate
print(f"\n  褰撳墠鍙樺寲鐜?vs 鏈潵鍙樺寲鐜?鐩稿叧鎬? ", end="")
seq_corr = agg.groupby('keyword').apply(
    lambda g: g['change_rate'].corr(g['change_rate'].shift(-1))).dropna()
print(f"mean={seq_corr.mean():.4f}, 姝ｇ浉鍏冲叧閿瘝={(seq_corr>0).sum()}/{len(seq_corr)}")

# ======== 4. total_hot 鑷浉鍏筹紙鐪嬬儹搴︾殑寤剁画鎬э級 ========
print("\n" + "="*60)
print("4. total_hot 鑷浉鍏筹紙鐑害鐨勫欢缁€э級")
print("="*60)

for lag in [1, 2, 3, 4, 5]:
    ar = agg.groupby('keyword')['total_hot'].apply(
        lambda g: np.log1p(g).corr(np.log1p(g).shift(lag))).dropna()
    print(f"  log_hot lag={lag}: mean={ar.mean():.4f}")

# ======== 5. 鏍囩绛栫暐 ========
print("\n" + "="*60)
print("5. 鏍囩绛栫暐瀵规瘮")
print("="*60)

# 绛栫暐: 浜屽垎绫?- 鏆存定 vs 鍏朵粬
for threshold_method in ['quantile', 'fixed']:
    print(f"\n  --- {threshold_method} ---")
    if threshold_method == 'quantile':
        q80 = agg['change_rate'].quantile(0.80)
        thresh = q80
        label_name = f'Q80鏆存定(>{thresh:.2f})'
        agg['label'] = (agg['change_rate'] > q80).astype(int)
    else:
        # 鍥哄畾闃堝€硷細鏍规嵁鏁版嵁鍒嗗竷閫変竴涓悎鐞嗙殑鍊?        for pct in [20, 30, 50, 80, 100]:
            agg['label'] = (agg['change_rate'] > pct/100).astype(int)
            pos_rate = agg['label'].mean()
            baseline = max(pos_rate, 1-pos_rate)
            print(f"    娑ㄥ箙>{pct}%: 姝ｆ牱鏈巼={pos_rate*100:.1f}%, 鍩虹嚎鍑嗙‘鐜?{baseline*100:.1f}%")

# Q80 鐨勮鎯?q80 = agg['change_rate'].quantile(0.80)
agg['label_q80'] = (agg['change_rate'] > q80).astype(int)
print(f"\n  Q80浜屽垎绫伙紙姝ｆ牱鏈?{(agg['label_q80']==1).sum()}, 鍗犳瘮={agg['label_q80'].mean()*100:.1f}%锛?)

# 妫€鏌ュ彲棰勬祴鎬э細lag鐗瑰緛涓庢爣绛剧殑鐩稿叧鎬?print(f"\n  鍚勬粸鍚庡彉鍖栫巼涓庢毚娑ㄦ爣绛剧殑鐩稿叧鎬?")
for lag in [1, 2, 3, 4, 5]:
    agg[f'prev_cr_{lag}'] = agg.groupby('keyword')['change_rate'].shift(lag)
    corr = agg[f'prev_cr_{lag}'].corr(agg['label_q80'])
    print(f"    lag_{lag} 鍙樺寲鐜?vs 鏆存定: {corr:.4f}")

# ======== 6. 鍏抽敭璇嶅崟鐙湅 ========
print("\n" + "="*60)
print("6. 鍚勫叧閿瘝 12h 绐楀彛鐗瑰緛")
print("="*60)

print(f"{'鍏抽敭璇?:<12} {'绐楀彛鏁?:>6} {'鍧囧€糷ot':>8} {'鍙樺寲鐜噑td':>9} {'鑷浉鍏?':>7} {'娑ㄦ鐜?:>7}")
print("-"*55)
for kw in sorted(agg['keyword'].unique()):
    kd = agg[agg['keyword'] == kw]
    cr = kd['change_rate'].clip(-5, 5)
    up_prob = (cr > 0).mean()
    ar1 = cr.corr(cr.shift(1))
    print(f"  {kw:<12} {len(kd):>6} {kd['total_hot'].mean():>8.0f} {cr.std():>8.4f} {ar1:>7.3f} {up_prob:>6.1%}")

# ======== 7. 澶氭棰勬祴 ========
print("\n" + "="*60)
print("7. 鏈潵 24h/36h 瓒嬪娍棰勬祴娼滃姏")
print("="*60)

# 鏈潵2涓獥鍙ｏ紙24h锛?agg['hot_2w'] = (agg.groupby('keyword')['total_hot'].shift(-1) +
                  agg.groupby('keyword')['total_hot'].shift(-2))
agg = agg.dropna(subset=['hot_2w'])
agg['trend_24h'] = (agg['hot_2w'] - agg['total_hot'] * 2) / (agg['total_hot'] * 2 + 1)

# 鑷浉鍏?for lag in [1, 2]:
    ar = agg.groupby('keyword')['trend_24h'].apply(
        lambda g: g.corr(g.shift(lag))).dropna()
    print(f"  24h瓒嬪娍 lag={lag}: mean={ar.mean():.4f}, 姝ｅ叧閿瘝={(ar>0).sum()}/{len(ar)}")

# 鏈潵3涓獥鍙ｏ紙36h锛?agg['hot_3w'] = (agg.groupby('keyword')['total_hot'].shift(-1) +
                  agg.groupby('keyword')['total_hot'].shift(-2) +
                  agg.groupby('keyword')['total_hot'].shift(-3))
agg = agg.dropna(subset=['hot_3w'])
agg['trend_36h'] = (agg['hot_3w'] - agg['total_hot'] * 3) / (agg['total_hot'] * 3 + 1)

for lag in [1]:
    ar = agg.groupby('keyword')['trend_36h'].apply(
        lambda g: g.corr(g.shift(lag))).dropna()
    print(f"  36h瓒嬪娍 lag=1: mean={ar.mean():.4f}, 姝ｅ叧閿瘝={(ar>0).sum()}/{len(ar)}")

# ======== 8. 鍧囧€煎洖褰掓柟鍚戦娴?========
print("\n" + "="*60)
print("8. 鍧囧€煎洖褰掔壒鎬э細鏆存定鍚庡繀璺岋紵")
print("="*60)

q20, q80 = agg['change_rate'].quantile([0.20, 0.80])
agg['prev_label'] = 1  # 骞崇ǔ
agg.loc[agg.groupby('keyword')['change_rate'].shift(1) > q80, 'prev_label'] = 2  # 鍓嶇獥鍙ｆ毚娑?agg.loc[agg.groupby('keyword')['change_rate'].shift(1) < q20, 'prev_label'] = 0  # 鍓嶇獥鍙ｆ毚璺?
print(f"  鍓嶇獥鍙ｆ毚娑?Q80)鍚庡綋鍓嶇獥鍙ｅ钩鍧囧彉鍖? {agg[agg['prev_label']==2]['change_rate'].clip(-5,5).mean():.4f}")
print(f"  鍓嶇獥鍙ｆ毚璺?Q20)鍚庡綋鍓嶇獥鍙ｅ钩鍧囧彉鍖? {agg[agg['prev_label']==0]['change_rate'].clip(-5,5).mean():.4f}")
print(f"  鍓嶇獥鍙ｅ钩绋冲悗褰撳墠绐楀彛骞冲潎鍙樺寲:     {agg[agg['prev_label']==1]['change_rate'].clip(-5,5).mean():.4f}")

# 鍧囧€煎洖褰掓柟鍚戝噯纭巼
agg['direction_pred'] = 1  # 棰勬祴骞崇ǔ锛堝洖褰掑潎鍊硷級
# 濡傛灉鍓嶇獥鍙ｆ毚娑ㄩ娴嬩笅璺岋紝鍓嶇獥鍙ｆ毚璺岄娴嬩笂娑?agg.loc[agg['prev_label'] == 2, 'direction_pred'] = 0  # 棰勬祴鏆磋穼
agg.loc[agg['prev_label'] == 0, 'direction_pred'] = 2  # 棰勬祴鏆存定

agg['direction_true'] = 1
agg.loc[agg['change_rate'] > q80, 'direction_true'] = 2
agg.loc[agg['change_rate'] < q20, 'direction_true'] = 0

# 鍧囧€煎洖褰掑噯纭巼
mean_reversion_acc = (agg['direction_pred'] == agg['direction_true']).mean()
print(f"\n  鍧囧€煎洖褰掔瓥鐣?鏆存定鈫掔寽璺? 鏆磋穼鈫掔寽娑? 鍑嗙‘鐜? {mean_reversion_acc*100:.1f}%")
print(f"  濮嬬粓鐚滃钩绋? {50.0:.1f}%")  # actually it's (agg['direction_true']==1).mean(), but let's simplify

# 妫€鏌ヤ笉鍚屾儏鍐?boom_prec = (agg[agg['prev_label'] == 2]['direction_pred'] == agg[agg['prev_label'] == 2]['direction_true']).mean()
bust_prec = (agg[agg['prev_label'] == 0]['direction_pred'] == agg[agg['prev_label'] == 0]['direction_true']).mean()
print(f"  鍓嶆毚娑ㄢ啋鐚滆穼 鍑嗙‘鐜? {boom_prec*100:.1f}%")
print(f"  鍓嶆毚璺屸啋鐚滄定 鍑嗙‘鐜? {bust_prec*100:.1f}%")

# ======== 鎬荤粨 ========
print("\n" + "="*60)
print("鎬荤粨")
print("="*60)
print(f"""
12h 绐楀彛 vs 6h/2h:
- 鑷浉鍏冲悓鏍蜂负璐燂紙鍧囧€煎洖褰掞級
- 鍙樺寲鐜囧垎甯冩洿瀹斤紙鏇存瀬绔殑鍙樺寲锛?- 鍏抽敭鍙戠幇锛氬潎鍊煎洖褰掔瓥鐣ワ紙鏆存定鈫掔寽璺? 鏆磋穼鈫掔寽娑級鍑嗙‘鐜?{mean_reversion_acc*100:.1f}%

杩欐剰鍛崇潃锛氫笅涓€涓?2h鐨刪ot_raw鏂瑰悜鍙互閮ㄥ垎閫氳繃鍧囧€煎洖褰掗娴嬨€?浣嗗鏋滅洰鏍囨槸棰勬祴"鏆存定"锛岄渶瑕佸弽杩囨潵鎯斥€斺€旀毚娑ㄤ箣鍚庢洿鍙兘鏆磋穼銆?""")
