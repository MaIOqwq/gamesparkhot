"""
鏁版嵁鎺㈢储鍒嗘瀽锛氭壘鍑烘渶閫傚悎棰勬祴鐨勭洰鏍囧拰绐楀彛
"""
import warnings
import numpy as np
import pandas as pd
import pymysql

warnings.filterwarnings('ignore')

# 璇绘暟鎹?conn = pymysql.connect(host='<SERVER_IP>', port=3306, user='spark',
                       password = <DB_PASSWORD>, database='standardized_data',
                       charset='utf8mb4')
df = pd.read_sql("SELECT * FROM standardized_data WHERE publish_time >= '2020-01-01' ORDER BY keyword, publish_time", conn)
conn.close()
print(f"鎬绘潯鏁? {len(df)}")
print(f"鍏抽敭璇? {df['keyword'].nunique()}")

df['publish_time'] = pd.to_datetime(df['publish_time'])

# ======== 1. 涓嶅悓绐楀彛澶у皬鐨勫彉鍖栫巼鍒嗗竷 ========
print("\n" + "="*60)
print("1. 涓嶅悓绐楀彛澶у皬鐨勫彉鍖栫巼鍒嗗竷")
print("="*60)

for window in ['2H', '6H', '24H']:
    df[f'win_{window}'] = df['publish_time'].dt.floor(window)
    agg = df.groupby(['keyword', f'win_{window}']).agg(
        total_hot=('hot_score', 'sum')).reset_index()
    agg = agg.sort_values(['keyword', f'win_{window}'])
    agg['change_rate'] = agg.groupby('keyword')['total_hot'].pct_change().fillna(0)
    agg['future_hot'] = agg.groupby('keyword')['total_hot'].shift(-1)
    agg['future_change'] = (agg['future_hot'] - agg['total_hot']) / (agg['total_hot'] + 1e-6)

    cr = agg['change_rate'].clip(-5, 5)
    fc = agg['future_change'].clip(-5, 5)

    print(f"\n  [{window}] 绐楀彛鏁? {len(agg)}, 鍏抽敭璇嶅潎鍊? {agg.groupby('keyword')['total_hot'].mean().mean():.0f}")
    print(f"  鍙樺寲鐜? mean={cr.mean():.4f}, std={cr.std():.4f}, skew={cr.skew():.2f}")
    print(f"  鏈潵鍙樺寲鐜? mean={fc.mean():.4f}, std={fc.std():.4f}")
    print(f"  鏈潵鍙樺寲鐜?鍒嗕綅鏁? 10%={fc.quantile(0.10):.4f}, 20%={fc.quantile(0.20):.4f}, 50%={fc.quantile(0.50):.4f}, 80%={fc.quantile(0.80):.4f}, 90%={fc.quantile(0.90):.4f}")

    # 鑷浉鍏虫€?(AR-1 of change_rate)
    kw_corr = agg.groupby('keyword').apply(
        lambda g: g['change_rate'].corr(g['change_rate'].shift(1))).dropna()
    print(f"  鑷浉鍏?1闃?: mean={kw_corr.mean():.4f}, 姝ｇ浉鍏冲崰姣?{(kw_corr>0).mean()*100:.0f}%")

    # 搴忓垪鐩稿叧鎬?(褰撳墠 change_rate 涓?鏈潵 change_rate 鐨勭浉鍏崇郴鏁?
    seq_corr = agg.groupby('keyword').apply(
        lambda g: g['change_rate'].corr(g['future_change'])).dropna()
    print(f"  褰撳墠->鏈潵鐩稿叧鎬? mean={seq_corr.mean():.4f}, 姝ｇ浉鍏冲崰姣?{(seq_corr>0).mean()*100:.0f}%")

# ======== 2. 鏆存定/鏆磋穼鐨勫彲棰勬祴鎬?========
print("\n" + "="*60)
print("2. 涓夌鏍囪绛栫暐瀵规瘮")
print("="*60)

for window in ['2H', '6H']:
    agg = df.groupby(['keyword', f'win_{window}']).agg(
        total_hot=('hot_score', 'sum')).reset_index()
    agg = agg.sort_values(['keyword', f'win_{window}'])
    agg['future_hot'] = agg.groupby('keyword')['total_hot'].shift(-1)
    agg = agg.dropna(subset=['future_hot'])
    agg['change_rate'] = (agg['future_hot'] - agg['total_hot']) / (agg['total_hot'] + 1e-6)

    # 鍏ㄥ眬鍒嗕綅鏁版爣绛?    q20, q80 = agg['change_rate'].quantile([0.20, 0.80])
    # 鍥哄畾闃堝€兼爣绛?(卤30%)
    # 鎸夊叧閿瘝鍒嗕綅鏁?
    # 绛栫暐 A: 鍏ㄥ眬鍒嗕綅鏁?(褰撳墠鍋氭硶)
    agg['label_global'] = 1  # 骞崇ǔ
    agg.loc[agg['change_rate'] > q80, 'label_global'] = 2  # 鏆存定
    agg.loc[agg['change_rate'] < q20, 'label_global'] = 0  # 鏆磋穼

    # 绛栫暐 B: 鍥哄畾闃堝€?    agg['label_fixed'] = 1
    agg.loc[agg['change_rate'] > 0.5, 'label_fixed'] = 2
    agg.loc[agg['change_rate'] < -0.3, 'label_fixed'] = 0

    # 绛栫暐 C: 浜屽垎绫?(鏆存定 vs 鍏朵粬, 鍏ㄥ眬Q80)
    agg['label_binary'] = 0
    agg.loc[agg['change_rate'] > q80, 'label_binary'] = 1

    # 绛栫暐 D: 浜屽垎绫?(鍥哄畾闃堝€?
    agg['label_binary_fixed'] = 0
    agg.loc[agg['change_rate'] > 0.5, 'label_binary_fixed'] = 1

    # 绛栫暐 E: 鏆存定/鏆磋穼鍚堝苟 (3绫烩啋2绫? 鍚堝苟娑ㄨ穼)
    agg['label_updown'] = 1  # 骞崇ǔ
    agg.loc[agg['change_rate'] > q80, 'label_updown'] = 2  # 娑?    agg.loc[agg['change_rate'] < q20, 'label_updown'] = 0  # 璺?
    # 妫€鏌ュ悇绫诲埆鐨勫钩琛℃€?    print(f"\n  [{window}]")
    # 妫€鏌ユ槸鍚︽湁鏄庢樉鐨勫彲棰勬祴淇″彿锛歝hange_rate 鍦ㄦ璐熶箣闂存槸鍚︽湁瑙勫緥
    # 璁＄畻"濡傛灉褰撳墠绐楀彛姝ｅ湪鏆存定锛屼笅涓€绐楀彛浼氭€庢牱"
    # 鎶婂綋鍓嶇獥鍙ｆ寜 change_rate 鍒嗙粍锛堟粸鍚庝竴闃讹級锛岀湅涓嬩竴绐楀彛鐨勫垎甯?    agg['prev_change'] = agg.groupby('keyword')['change_rate'].shift(1)
    current_boom = agg[agg['prev_change'] > q80]['change_rate']
    current_bust = agg[agg['prev_change'] < q20]['change_rate']
    current_stable = agg[(agg['prev_change'] >= q20) & (agg['prev_change'] <= q80)]['change_rate']

    print(f"  鍓嶇獥鍙ｆ毚娑?-> 涓嬩竴绐楀彛 骞冲潎鍙樺寲: {current_boom.mean():.4f}")
    print(f"  鍓嶇獥鍙ｆ毚璺?-> 涓嬩竴绐楀彛 骞冲潎鍙樺寲: {current_bust.mean():.4f}")
    print(f"  鍓嶇獥鍙ｅ钩绋?-> 涓嬩竴绐楀彛 骞冲潎鍙樺寲: {current_stable.mean():.4f}")

    # 绛栫暐璇勪及: 鐪嬩笉鍚屾爣绛惧垎甯?    for name, col in [('鍏ㄥ眬3鍒嗙被', 'label_global'), ('鍥哄畾闃堝€?鍒嗙被', 'label_fixed'),
                       ('鍏ㄥ眬浜屽垎绫?, 'label_binary'), ('鍥哄畾闃堝€间簩鍒嗙被', 'label_binary_fixed')]:
        vc = agg[col].value_counts(normalize=True).sort_index()
        majority = vc.max()
        print(f"  {name}: {vc.to_dict()} (澶氭暟绫诲崰姣?{majority*100:.1f}%, 鍩虹嚎鍑嗙‘鐜?{majority*100:.1f}%)")

# ======== 3. 鍏抽敭璇嶇骇鍒殑宸紓 ========
print("\n" + "="*60)
print("3. 鍚勫叧閿瘝鐨勬尝鍔ㄧ壒寰?)
print("="*60)

df['win_6H'] = df['publish_time'].dt.floor('6H')
agg6 = df.groupby(['keyword', 'win_6H']).agg(
    total_hot=('hot_score', 'sum')).reset_index()
agg6 = agg6.sort_values(['keyword', 'win_6H'])
agg6['future_hot'] = agg6.groupby('keyword')['total_hot'].shift(-1)
agg6 = agg6.dropna(subset=['future_hot'])
agg6['change_rate'] = (agg6['future_hot'] - agg6['total_hot']) / (agg6['total_hot'] + 1e-6)

print(f"{'鍏抽敭璇?:<12} {'绐楀彛鏁?:>6} {'鍧囧€糷ot':>8} {'鍙樺寲鐜噑td':>9} {'鑷浉鍏?:>7} {'娑ㄦ鐜?:>7}")
print("-"*55)
for kw in sorted(agg6['keyword'].unique()):
    kd = agg6[agg6['keyword'] == kw]
    cr = kd['change_rate'].clip(-5, 5)
    up_prob = (cr > 0).mean()
    ar1 = cr.corr(cr.shift(1))
    print(f"  {kw:<12} {len(kd):>6} {kd['total_hot'].mean():>8.0f} {cr.std():>8.4f}  {ar1:>6.3f} {up_prob:>6.1%}")

# ======== 4. 浠€涔堟牱鐨勯娴嬫洿鏈夋剰涔?========
print("\n" + "="*60)
print("4. 澶氭棰勬祴娼滃姏 (鏈潵24h)")
print("="*60)

# 鐢?h绐楀彛棰勬祴鏈潵24h鐨勮蛋鍚?agg6['hot_4w'] = (agg6.groupby('keyword')['total_hot']
                   .shift(-1) + agg6.groupby('keyword')['total_hot']
                   .shift(-2) + agg6.groupby('keyword')['total_hot']
                   .shift(-3) + agg6.groupby('keyword')['total_hot']
                   .shift(-4))
agg6 = agg6.dropna(subset=['hot_4w'])
agg6['trend_24h'] = (agg6['hot_4w'] - agg6['total_hot'] * 4) / (agg6['total_hot'] * 4 + 1)

# 24h瓒嬪娍鐨勫垎浣嶆暟
print(f"  24h 鍙樺寲鐜?(鏈潵4涓?h绐楀彛 vs 褰撳墠4鍊?:")
print(f"    mean={agg6['trend_24h'].mean():.4f}, std={agg6['trend_24h'].std():.4f}")
for q in [10, 20, 30, 50, 70, 80, 90]:
    print(f"    P{q}={agg6['trend_24h'].quantile(q/100):.4f}")

# 濡傛灉棰勬祴銆屾湭鏉?4h浼氭毚娑ㄣ€?trend_24h > P80) 鈫?浜屽垎绫?agg6['label_24h'] = 0
agg6.loc[agg6['trend_24h'] > agg6['trend_24h'].quantile(0.80), 'label_24h'] = 1
vc24 = agg6['label_24h'].value_counts(normalize=True)
print(f"  24h鏆存定鏍囩鍒嗗竷: {vc24.to_dict()} (鍩虹嚎={vc24.max()*100:.1f}%)")

# 妫€鏌ヨ嚜鐩稿叧 (鏇撮暱鐨勮蹇?
for lag in [1, 2, 3, 4, 5]:
    ar = agg6.groupby('keyword')['trend_24h'].apply(
        lambda g: g.corr(g.shift(lag))).dropna()
    print(f"  24h瓒嬪娍鑷浉鍏?lag={lag}: mean={ar.mean():.4f}")

# ======== 5. 鎬荤粨 ========
print("\n" + "="*60)
print("5. 缁撹")
print("="*60)
print("""
浠庡悇绐楀彛鐨勫彉鍖栫巼鍜岀浉鍏虫€ф潵鐪嬶紝2h/6h 绐楀彛鐨勭煭鏈熷彉鍖栫巼鍩烘湰鏄櫧鍣０锛?鑷浉鍏崇郴鏁版帴杩?0锛屽綋鍓?>鏈潵鍙樺寲鐜囩浉鍏虫€т篃鏋佷綆銆?
杩欒鏄庯細绮剧‘棰勬祴銆屼笅涓€涓獥鍙ｇ殑娑ㄨ穼銆嶅嚑涔庝笉鍙兘銆?
鏇存湁娼滃姏鐨勬柟鍚戯細
  1. 浜屽垎绫汇€屾湭鏉?24h 鏄惁浼氱垎鍙戙€?- 鏇撮暱鐨勬椂闂寸獥鍙ｏ紝鏇村鐨勭疮绉俊鍙?  2. 鎸夊叧閿瘝鍗曠嫭寤烘ā - 涓嶅悓鍏抽敭璇嶇殑娉㈠姩妯″紡涓嶅悓
  3. 鐢ㄥ浐瀹氶槇鍊间唬鏇垮垎浣嶆暟鏍囩 - 纭繚鏍囨敞鐨?鏆存定"纭疄鏄湁鎰忎箟鐨勬定骞?""")
