#!/usr/bin/env python3
"""
蹇€熻缁?+ 铻嶅悎 鈫?9:15鍑烘ā鍨嬶紝9:30閮ㄧ讲瀹屾垚
"""
import os, sys, pymysql, pandas as pd, numpy as np, pickle, json, logging, warnings
from datetime import datetime
import time as _time
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.utils.class_weight import compute_class_weight
from xgboost import XGBClassifier
import multiprocessing as mp
warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB = dict(host='<SERVER_IP>', port=3306, user='spark', password = <DB_PASSWORD>, database='standardized_data')
N_WORKERS = 14
N_TRIALS = 50

def load_data():
    conn = pymysql.connect(**DB, charset='utf8mb4', connect_timeout=10, read_timeout=300)
    t = datetime.now()
    df = pd.read_sql("SELECT * FROM standardized_data WHERE publish_time >= '2020-01-01' ORDER BY keyword, publish_time", conn)
    conn.close()
    logger.info(f"鏁版嵁: {len(df)}鏉? {df['keyword'].nunique()}鍏抽敭璇? 鑰楁椂{(datetime.now()-t).total_seconds():.0f}s")
    return df

def build_features(df, extra_cols=None):
    """鐗瑰緛宸ョ▼"""
    df = df.copy()
    df['publish_time'] = pd.to_datetime(df['publish_time'])
    df['window_start'] = df['publish_time'].dt.floor('2H')

    agg = {'hot_score': 'sum', 'like_count': 'mean', 'comment_count': 'mean',
           'sentiment_score': 'mean', 'id': 'count'}
    if extra_cols:
        agg.update(extra_cols)

    out = df.groupby(['keyword', 'window_start']).agg(agg).reset_index()
    rename = {'hot_score': 'total_hot', 'like_count': 'avg_like', 'comment_count': 'avg_comment',
              'sentiment_score': 'avg_sentiment', 'id': 'count',
              'view_count': 'avg_view', 'coin_count': 'avg_coin', 'favorite_count': 'avg_favorite',
              'share_count': 'avg_share', 'danmaku_count': 'avg_danmaku',
              'text_length': 'text_len_avg'}
    out.rename(columns={k: v for k, v in rename.items() if k in out.columns}, inplace=True)

    out['hour'] = out['window_start'].dt.hour
    out['day_of_week'] = out['window_start'].dt.dayofweek
    out['is_weekend'] = (out['day_of_week'] >= 5).astype(int)
    out['month'] = out['window_start'].dt.month

    # 婊炲悗鐗瑰緛
    lag_cols = ['total_hot', 'avg_sentiment', 'count', 'avg_like', 'avg_comment']
    for c in lag_cols:
        if c not in out.columns: continue
        for i in range(1, 4):
            out[f'lag_{i}_{c}'] = out.groupby('keyword')[c].shift(i)

    l1 = out['lag_1_total_hot'].fillna(0) if 'lag_1_total_hot' in out.columns else out['total_hot']
    out['total_hot_change_rate'] = (out['total_hot'] - l1) / (l1 + 1e-6)
    r = out.groupby('keyword')['total_hot'].rolling(6)
    out['rolling_mean_6_total_hot'] = r.mean().reset_index(level=0, drop=True)
    out['rolling_std_6_total_hot'] = r.std().reset_index(level=0, drop=True)
    return out

def get_features():
    return ['keyword_enc', 'total_hot', 'count', 'avg_sentiment', 'avg_like', 'avg_comment',
            'lag_1_total_hot', 'lag_2_total_hot', 'lag_3_total_hot',
            'lag_1_avg_sentiment', 'lag_2_avg_sentiment', 'lag_3_avg_sentiment',
            'lag_1_count', 'lag_2_count', 'lag_3_count',
            'lag_1_avg_like', 'lag_2_avg_like', 'lag_3_avg_like',
            'lag_1_avg_comment', 'lag_2_avg_comment', 'lag_3_avg_comment',
            'total_hot_change_rate', 'rolling_mean_6_total_hot', 'rolling_std_6_total_hot',
            'hour', 'day_of_week', 'is_weekend', 'month']

def prep_data(processed, le, shift=-1, thresh=0.1):
    """鍑嗗璁粌鏁版嵁"""
    df = processed.copy()
    df['future_total_hot'] = df.groupby('keyword')['total_hot'].shift(shift)
    df = df.dropna(subset=['future_total_hot']).copy()
    cr = (df['future_total_hot'] - df['total_hot']) / (df['total_hot'] + 1e-6)
    df['label'] = 1
    df.loc[cr > thresh, 'label'] = 2
    df.loc[cr < -thresh, 'label'] = 0
    df = df.fillna(0)
    df['keyword_enc'] = le.transform(df['keyword'])
    return df

def train_single(args):
    """璁粌鍗曚釜妯″瀷锛堢敤浜庡杩涚▼锛?""
    idx, X_tr, y_tr, sw, X_v, y_v, X_te, y_te, hp = args
    try:
        params = {'objective': 'multi:softprob', 'num_class': 3, 'eval_metric': 'mlogloss',
                  'random_state': 42 + idx, 'verbosity': 0, 'n_jobs': 1}
        params.update(hp)
        m = XGBClassifier(**params)
        m.fit(X_tr, y_tr, sample_weight=sw, eval_set=[(X_v, y_v)], early_stopping_rounds=30, verbose=False)
        yp = m.predict(X_te)
        acc = accuracy_score(y_te, yp)
        f1 = f1_score(y_te, yp, average='macro', zero_division=0)
        r = classification_report(y_te, yp, output_dict=True, zero_division=0)
        dr = r.get('0', {}).get('recall', 0)
        ur = r.get('2', {}).get('recall', 0)
        comp = acc * 0.4 + f1 * 0.3 + dr * 0.15 + ur * 0.15
        return {'model': m, 'acc': acc, 'f1': f1, 'comp': comp, 'down_r': dr, 'up_r': ur, 'hp': hp}
    except Exception as e:
        return None

def sequential_search(X_tr, y_tr, sw, X_v, y_v, X_te, y_te):
    """椤哄簭鎼滅储鍙傛暟锛堝疄鏃舵樉绀烘瘡杞繘搴︼級"""
    param_pool = [
        {'max_depth': d, 'learning_rate': lr, 'n_estimators': n,
         'subsample': ss, 'colsample_bytree': cs,
         'reg_lambda': rl, 'reg_alpha': ra, 'min_child_weight': mw, 'gamma': g}
        for d in [3, 4, 5, 6] for lr in [0.01, 0.02, 0.03, 0.05]
        for n in [500, 800, 1000] for ss in [0.7, 0.8, 0.85]
        for cs in [0.7, 0.8, 0.85] for rl in [1.0, 2.0, 3.0]
        for ra in [0.1, 0.3, 0.5, 1.0] for mw in [1, 3, 5] for g in [0, 0.1, 0.2]
    ]
    rng = np.random.RandomState(42)
    total = min(N_TRIALS, len(param_pool))
    selected = rng.choice(len(param_pool), size=total, replace=False)
    tasks = [param_pool[int(i)] for i in selected]
    logger.info(f"椤哄簭璁粌 {total} 涓ā鍨?..")
    t0 = datetime.now()
    results = []
    best_comp = -1
    for i, hp in enumerate(tasks):
        t1 = _time.time()
        res = train_single((i, X_tr, y_tr, sw, X_v, y_v, X_te, y_te, hp))
        elapsed = _time.time() - t1
        if res is not None:
            results.append(res)
            if res['comp'] > best_comp:
                best_comp = res['comp']
                logger.info(f"  [{i+1}/{total}] new-best: comp={res['comp']:.4f} "
                            f"acc={res['acc']:.4f} f1={res['f1']:.4f} "
                            f"lr={hp['learning_rate']} d={hp['max_depth']} n={hp['n_estimators']} "
                            f"({elapsed:.1f}s)")
            else:
                logger.info(f"  [{i+1}/{total}] comp={res['comp']:.4f} acc={res['acc']:.4f} "
                            f"(best={best_comp:.4f}) ({elapsed:.1f}s)")
    elapsed = (datetime.now() - t0).total_seconds()
    logger.info(f"瀹屾垚 {len(results)}/{total} 涓? 鎬昏€楁椂{elapsed:.0f}s")
    results.sort(key=lambda x: x['comp'], reverse=True)
    return results

def train_ensemble(models, X_tr, y_tr, X_te, y_te):
    """杞姇绁ㄨ瀺鍚?""
    from sklearn.ensemble import VotingClassifier
    est = [(f'm{i}', r['model']) for i, r in enumerate(models[:5])]
    ens = VotingClassifier(estimators=est, voting='soft')
    ens.fit(X_tr, y_tr)
    yp = ens.predict(X_te)
    acc = accuracy_score(y_te, yp)
    f1 = f1_score(y_te, yp, average='macro', zero_division=0)
    r = classification_report(y_te, yp, output_dict=True, zero_division=0)
    dr = r.get('0', {}).get('recall', 0)
    ur = r.get('2', {}).get('recall', 0)
    comp = acc * 0.4 + f1 * 0.3 + dr * 0.15 + ur * 0.15
    return ens, {'acc': acc, 'f1': f1, 'comp': comp, 'down_r': dr, 'up_r': ur}

def deploy_to_server():
    """閮ㄧ讲妯″瀷鍒版湇鍔″櫒"""
    import subprocess, glob
    # 鎵惧埌鏈€鏂扮殑妯″瀷鏂囦欢
    src_dir = os.path.join(os.path.dirname(__file__), 'final_model')
    dst_dir = '/opt/opinion-analysis/predict/'

    # 浼犺緭 model.pkl, feature_columns.pkl, label_encoder.pkl
    key = '<SSH_KEY_PATH>'
    host = 'root@<SERVER_IP>'

    files = ['model.pkl', 'feature_columns.pkl', 'label_encoder.pkl', 'class_map.pkl']
    for f in files:
        local = os.path.join(src_dir, f)
        if os.path.exists(local):
            cmd = f'scp -i "{key}" -o StrictHostKeyChecking=no "{local}" {host}:{dst_dir}'
            subprocess.run(cmd, shell=True, check=True)
            logger.info(f"涓婁紶 {f}")

    # 閲嶅惎鏈嶅姟
    cmd = f'ssh -i "{key}" -o StrictHostKeyChecking=no {host} "systemctl restart opinion-predict.service"'
    subprocess.run(cmd, shell=True, check=True)
    logger.info("鏈嶅姟宸查噸鍚?)

    # 楠岃瘉
    cmd = f'ssh -i "{key}" -o StrictHostKeyChecking=no {host} "sleep 3 && curl -s http://127.0.0.1:5000/api/predict/trend?keyword=test"'
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    logger.info(f"楠岃瘉缁撴灉: {r.stdout[:200]}")


def main():
    logger.info("=" * 60)
    logger.info("蹇€熻缁?+ 妯″瀷铻嶅悎 鍚姩")
    logger.info("=" * 60)

    # 1. 鍔犺浇鏁版嵁锛堜竴娆℃€э級
    raw = load_data()
    le = LabelEncoder()
    le.fit(raw['keyword'].unique())
    logger.info(f"鍏抽敭璇? {len(le.classes_)}涓?)

    # 2. 鐗瑰緛宸ョ▼锛坱2绾у埆锛氭牳蹇?like/comment/text锛?    extra = {'view_count': 'mean', 'coin_count': 'mean', 'favorite_count': 'mean',
             'share_count': 'mean', 'danmaku_count': 'mean', 'text_length': 'mean'}
    processed = build_features(raw, extra)
    features = get_features()
    logger.info(f"鐗瑰緛: {len(features)}涓? 鏍锋湰: {len(processed)}")

    # 3. 鍙窇2缁勫疄楠岋紙2h棰勬祴, 涓嶅悓闃堝€硷級
    experiments = [
        ('th0.10', -1, 0.10),
        ('th0.08', -1, 0.08),
    ]

    all_top = []
    best = {'comp': -1}

    for exp_name, shift, thresh in experiments:
        logger.info(f"\n--- 瀹為獙: {exp_name} (shift={-shift*2}h, thresh={thresh}) ---")
        df = prep_data(processed, le, shift, thresh)

        train = df[df['window_start'] <= '2024-12-31']
        val = df[(df['window_start'] > '2024-12-31') & (df['window_start'] <= '2025-12-31')]
        test = df[df['window_start'] > '2025-12-31']
        logger.info(f"train={len(train)} val={len(val)} test={len(test)}")
        logger.info(f"绫诲埆: {train['label'].value_counts().to_dict()}")

        X_tr, y_tr = train[features], train['label']
        X_v, y_v = val[features], val['label']
        X_te, y_te = test[features], test['label']

        cw = compute_class_weight('balanced', classes=np.unique(y_tr), y=y_tr)
        sw = np.array([dict(zip(np.unique(y_tr), cw))[l] for l in y_tr])

        # 椤哄簭鎼滅储锛堝疄鏃舵樉绀烘瘡杞繘搴︼級
        results = sequential_search(X_tr, y_tr, sw, X_v, y_v, X_te, y_te)

        # 璁板綍top
        for r in results[:5]:
            all_top.append(r)

        if results[0]['comp'] > best['comp']:
            best = {
                'comp': results[0]['comp'], 'acc': results[0]['acc'],
                'f1': results[0]['f1'], 'down_r': results[0]['down_r'],
                'up_r': results[0]['up_r'],
                'model': results[0]['model'], 'params': results[0]['hp'],
                'X_tr': X_tr, 'y_tr': y_tr,
                'X_te': X_te, 'y_te': y_te,
            }
            logger.info(f"  鏂版渶浣? acc={results[0]['acc']:.4f} comp={results[0]['comp']:.4f}")

    # 4. 铻嶅悎 Top5
    all_top.sort(key=lambda x: x['comp'], reverse=True)
    logger.info(f"\n鍗曟ā鍨嬫渶浣? acc={best['acc']:.4f} comp={best['comp']:.4f}")

    ensemble, em = train_ensemble(all_top[:5], best['X_tr'], best['y_tr'], best['X_te'], best['y_te'])
    logger.info(f"铻嶅悎妯″瀷  : acc={em['acc']:.4f} comp={em['comp']:.4f}")

    # 5. 閫夋嫨鏇村ソ鐨?    use_ens = em['comp'] > best['comp']
    final = ensemble if use_ens else best['model']
    fin_type = 'Voting Ensemble' if use_ens else 'Single XGBoost'
    metrics = em if use_ens else best
    logger.info(f"\n鏈€缁堟ā鍨? {fin_type}")
    logger.info(f"acc={metrics['acc']:.4f} f1={metrics['f1']:.4f} comp={metrics['comp']:.4f}")
    logger.info(f"涓嬮檷鍙洖={metrics['down_r']:.4f} 涓婂崌鍙洖={metrics['up_r']:.4f}")

    # 淇濆瓨
    out = 'final_model'
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'model.pkl'), 'wb') as f:
        pickle.dump(final, f)
    with open(os.path.join(out, 'feature_columns.pkl'), 'wb') as f:
        pickle.dump(features, f)
    with open(os.path.join(out, 'label_encoder.pkl'), 'wb') as f:
        pickle.dump(le, f)
    with open(os.path.join(out, 'class_map.pkl'), 'wb') as f:
        pickle.dump({0: '涓嬮檷', 1: '骞崇ǔ', 2: '涓婂崌'}, f)
    json.dump({k: float(v) if isinstance(v, (np.floating,)) else v
               for k, v in metrics.items()}, open(os.path.join(out, 'metrics.json'), 'w'),
              ensure_ascii=False, indent=2)
    logger.info(f"妯″瀷宸蹭繚瀛樺埌 {out}/")

    # 6. 閮ㄧ讲
    logger.info("\n寮€濮嬮儴缃插埌鏈嶅姟鍣?..")
    deploy_to_server()
    logger.info("閮ㄧ讲瀹屾垚!")

if __name__ == '__main__':
    mp.freeze_support()
    main()
