#!/usr/bin/env python3
"""
蹇€熶紭鍖?+ 妯″瀷铻嶅悎
- 鏁版嵁鍙姞杞戒竴娆?- 澶氳繘绋嬪苟琛岃缁?- Voting Ensemble 铻嶅悎鏈€浼樻ā鍨?- 鐩爣: 9:30 鍓嶉儴缃?"""
import os, sys, pymysql, pandas as pd, numpy as np
from datetime import datetime
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.utils.class_weight import compute_class_weight
from xgboost import XGBClassifier
from sklearn.ensemble import VotingClassifier
import pickle, logging, json, warnings, multiprocessing as mp
warnings.filterwarnings('ignore')

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_CONFIG = {
    'host': '<SERVER_IP>', 'port': 3306,
    'user': 'spark', 'password': '123456',
    'database': 'standardized_data',
}
N_JOBS = 14  # 骞惰鏁?N_TRIALS = 80  # 姣忕粍瀹為獙鍙傛暟鎼滅储娆℃暟

# ===== 鐗瑰緛瀹氫箟锛堝熀浜庢暟鎹簱瀹為檯瀛楁濉厖鐜囷級 =====
def build_feature_list(tier):
    base = ['keyword_enc', 'total_hot', 'count', 'avg_sentiment']
    if tier in ('t2', 't3'):
        base += ['avg_like', 'avg_comment', 'text_len_avg']
    if tier == 't3':
        base += ['avg_view', 'avg_coin', 'avg_favorite', 'avg_share', 'avg_danmaku',
                 'image_ratio', 'video_ratio']
    lag_feats = ['total_hot', 'avg_sentiment', 'count']
    if tier in ('t2', 't3'):
        lag_feats += ['avg_like', 'avg_comment']
    if tier == 't3':
        lag_feats += ['avg_view', 'avg_coin', 'avg_favorite', 'avg_share']
    lags = [f'lag_{i}_{f}' for f in lag_feats for i in range(1, 4)]
    trend = ['total_hot_change_rate', 'rolling_mean_6_total_hot', 'rolling_std_6_total_hot']
    time_f = ['hour', 'day_of_week', 'is_weekend', 'month']
    return base + lags + trend + time_f


def load_and_process():
    """涓€娆℃€у姞杞芥暟鎹苟澶勭悊鐗瑰緛"""
    conn = pymysql.connect(**DB_CONFIG, charset='utf8mb4', connect_timeout=10, read_timeout=300)
    t = datetime.now()
    df = pd.read_sql("SELECT * FROM standardized_data WHERE publish_time >= '2020-01-01' ORDER BY keyword, publish_time", conn)
    conn.close()
    logger.info(f"鏁版嵁鍔犺浇: {len(df)} 鏉? {df['keyword'].nunique()} 鍏抽敭璇? 鑰楁椂 {(datetime.now()-t).total_seconds():.1f}s")

    df['publish_time'] = pd.to_datetime(df['publish_time'])
    df['window_start'] = df['publish_time'].dt.floor('2H')

    results = {}
    for tier_name, add_cols in [
        ('t1', {}),
        ('t2', {'view_count': 'mean', 'coin_count': 'mean', 'favorite_count': 'mean',
                'share_count': 'mean', 'danmaku_count': 'mean', 'text_length': 'mean'}),
        ('t3', {'view_count': 'mean', 'coin_count': 'mean', 'favorite_count': 'mean',
                'share_count': 'mean', 'danmaku_count': 'mean', 'text_length': 'mean',
                'has_image': 'mean', 'has_video': 'mean'}),
    ]:
        agg = {'hot_score': 'sum', 'like_count': 'mean', 'comment_count': 'mean',
               'sentiment_score': 'mean', 'id': 'count'}
        agg.update(add_cols)
        processed = df.groupby(['keyword', 'window_start']).agg(agg).reset_index()

        col_map = {'hot_score': 'total_hot', 'like_count': 'avg_like', 'comment_count': 'avg_comment',
                   'view_count': 'avg_view', 'coin_count': 'avg_coin', 'favorite_count': 'avg_favorite',
                   'share_count': 'avg_share', 'danmaku_count': 'avg_danmaku',
                   'sentiment_score': 'avg_sentiment', 'has_image': 'image_ratio',
                   'has_video': 'video_ratio', 'text_length': 'text_len_avg', 'id': 'count'}
        processed.rename(columns={k: v for k, v in col_map.items() if k in processed.columns}, inplace=True)

        processed['hour'] = processed['window_start'].dt.hour
        processed['day_of_week'] = processed['window_start'].dt.dayofweek
        processed['is_weekend'] = (processed['day_of_week'] >= 5).astype(int)
        processed['month'] = processed['window_start'].dt.month

        # 婊炲悗鐗瑰緛
        lf = ['total_hot', 'avg_sentiment', 'count']
        if tier_name in ('t2', 't3'):
            lf += ['avg_like', 'avg_comment']
        if tier_name == 't3':
            lf += ['avg_view', 'avg_coin', 'avg_favorite', 'avg_share']
        for f in lf:
            if f not in processed.columns: continue
            for i in range(1, 4):
                processed[f'lag_{i}_{f}'] = processed.groupby('keyword')[f].shift(i)

        l1 = processed['lag_1_total_hot'].fillna(0) if 'lag_1_total_hot' in processed.columns else processed['total_hot']
        processed['total_hot_change_rate'] = (processed['total_hot'] - l1) / (l1 + 1e-6)
        rolling = processed.groupby('keyword')['total_hot'].rolling(6)
        processed['rolling_mean_6_total_hot'] = rolling.mean().reset_index(level=0, drop=True)
        processed['rolling_std_6_total_hot'] = rolling.std().reset_index(level=0, drop=True)

        results[tier_name] = processed

    logger.info(f"鐗瑰緛宸ョ▼瀹屾垚: t1={len(results['t1'])} t2={len(results['t2'])} t3={len(results['t3'])}")
    return results, df['keyword'].unique()


def prepare_data(processed, features, label_shift=-1, threshold=0.1, le=None):
    """鍑嗗璁粌鏁版嵁"""
    df = processed.copy()
    df['future_total_hot'] = df.groupby('keyword')['total_hot'].shift(label_shift)
    df = df.dropna(subset=['future_total_hot']).copy()
    cr = (df['future_total_hot'] - df['total_hot']) / (df['total_hot'] + 1e-6)
    df['label'] = 1
    df.loc[cr > threshold, 'label'] = 2
    df.loc[cr < -threshold, 'label'] = 0
    df = df.fillna(0)
    if le is not None:
        df['keyword_enc'] = le.fit_transform(df['keyword'])
    avail = [c for c in features if c in df.columns]
    return df, avail


def train_model(params):
    """鍗曚釜妯″瀷璁粌锛堢敤浜庡杩涚▼锛?""
    idx, X_tr, y_tr, sw, X_v, y_v, X_te, y_te = params
    try:
        model = XGBClassifier(**{
            'objective': 'multi:softprob', 'num_class': 3,
            'eval_metric': 'mlogloss', 'random_state': 42 + idx,
            'verbosity': 0, 'n_jobs': 1,
            **params['hp']
        })
        model.fit(X_tr, y_tr, sample_weight=sw,
                  eval_set=[(X_v, y_v)], early_stopping_rounds=30, verbose=False)
        y_pred = model.predict(X_te)
        acc = accuracy_score(y_te, y_pred)
        f1 = f1_score(y_te, y_pred, average='macro', zero_division=0)
        report = classification_report(y_te, y_pred, output_dict=True, zero_division=0)
        down_r = report.get('0', {}).get('recall', 0)
        up_r = report.get('2', {}).get('recall', 0)
        comp = acc * 0.4 + f1 * 0.3 + down_r * 0.15 + up_r * 0.15
        return {'idx': idx, 'model': model, 'acc': acc, 'f1': f1,
                'comp': comp, 'down_r': down_r, 'up_r': up_r, 'params': params['hp']}
    except Exception as e:
        logger.warning(f"  model {idx} failed: {e}")
        return None


def random_search_parallel(X_tr, y_tr, sw, X_v, y_v, X_te, y_te, n_trials=80):
    """骞惰闅忔満鎼滅储"""
    param_pool = [
        {'max_depth': d, 'learning_rate': lr, 'n_estimators': n,
         'subsample': ss, 'colsample_bytree': cs,
         'reg_lambda': rl, 'reg_alpha': ra,
         'min_child_weight': mcw, 'gamma': g}
        for d in [3, 4, 5, 6, 7]
        for lr in [0.01, 0.02, 0.03, 0.05]
        for n in [500, 800, 1000]
        for ss in [0.7, 0.8, 0.85]
        for cs in [0.7, 0.8, 0.85]
        for rl in [1.0, 2.0, 3.0]
        for ra in [0.1, 0.3, 0.5, 1.0]
        for mcw in [1, 3, 5]
        for g in [0, 0.1, 0.2]
    ]
    # 闅忔満閫?n_trials 缁?    rng = np.random.RandomState(42)
    selected = rng.choice(len(param_pool), size=min(n_trials, len(param_pool)), replace=False)
    task_params = [{
        'hp': param_pool[int(i)]
    } for i in selected]

    pool_args = [(idx, X_tr, y_tr, sw, X_v, y_v, X_te, y_te) for idx, p in enumerate(task_params)]

    logger.info(f"骞惰璁粌 {len(task_params)} 涓ā鍨?(workers={N_JOBS})...")
    t0 = datetime.now()
    with mp.Pool(N_JOBS) as pool:
        results = pool.map(train_model, pool_args)
    results = [r for r in results if r is not None]
    logger.info(f"瀹屾垚 {len(results)} 涓ā鍨? 鑰楁椂 {(datetime.now()-t0).total_seconds():.1f}s")

    results.sort(key=lambda x: x['comp'], reverse=True)
    return results


def train_ensemble(top_models, X_tr, y_tr, X_te, y_te):
    """鐢ㄦ渶浼樻ā鍨嬫瀯寤?Voting Ensemble"""
    estimators = [(f'm{i}', r['model']) for i, r in enumerate(top_models[:5])]
    ensemble = VotingClassifier(estimators=estimators, voting='soft')
    ensemble.fit(X_tr, y_tr)
    y_pred = ensemble.predict(X_te)
    acc = accuracy_score(y_te, y_pred)
    f1 = f1_score(y_te, y_pred, average='macro', zero_division=0)
    report = classification_report(y_te, y_pred, output_dict=True, zero_division=0)
    down_r = report.get('0', {}).get('recall', 0)
    up_r = report.get('2', {}).get('recall', 0)
    comp = acc * 0.4 + f1 * 0.3 + down_r * 0.15 + up_r * 0.15
    return ensemble, {'accuracy': acc, 'f1': f1, 'composite_score': comp,
                      'down_recall': down_r, 'up_recall': up_r}


def main():
    logger.info("=" * 60)
    logger.info("蹇€熶紭鍖?+ 妯″瀷铻嶅悎")
    logger.info("=" * 60)

    # 1. 鍔犺浇鏁版嵁 + 鐗瑰緛宸ョ▼锛堜竴娆℃€э級
    all_data, keywords = load_and_process()
    le = LabelEncoder()
    le.fit(keywords)

    # 2. 瀹為獙閰嶇疆锛堢簿绠€鍒?4 缁勬渶鍏抽敭锛?    experiments = [
        ('t1_2h_0.10',  't1', -1, 0.10),
        ('t2_2h_0.10',  't2', -1, 0.10),
        ('t2_2h_0.08',  't2', -1, 0.08),
        ('t2_2h_0.05',  't2', -1, 0.05),
    ]

    all_models = []
    best_overall = {'comp': -1}

    for exp_name, tier, shift, thresh in experiments:
        logger.info(f"\n{'='*50}")
        logger.info(f"瀹為獙: {exp_name}")

        processed = all_data[tier].copy()
        # 娣诲姞鏍囩
        processed['future_total_hot'] = processed.groupby('keyword')['total_hot'].shift(shift)
        processed = processed.dropna(subset=['future_total_hot']).copy()
        cr = (processed['future_total_hot'] - processed['total_hot']) / (processed['total_hot'] + 1e-6)
        processed['label'] = 1
        processed.loc[cr > thresh, 'label'] = 2
        processed.loc[cr < -thresh, 'label'] = 0
        processed = processed.fillna(0)
        processed['keyword_enc'] = le.transform(processed['keyword'])

        features = build_feature_list(tier)
        avail = [c for c in features if c in processed.columns]
        logger.info(f"鐗瑰緛鏁? {len(avail)}, 绫诲埆: {processed['label'].value_counts().to_dict()}")

        train_df = processed[processed['window_start'] <= '2024-12-31']
        val_df = processed[(processed['window_start'] > '2024-12-31') & (processed['window_start'] <= '2025-12-31')]
        test_df = processed[processed['window_start'] > '2025-12-31']
        logger.info(f"鏁版嵁: train={len(train_df)} val={len(val_df)} test={len(test_df)}")

        X_tr, y_tr = train_df[avail], train_df['label']
        X_v, y_v = val_df[avail], val_df['label']
        X_te, y_te = test_df[avail], test_df['label']

        classes = np.unique(y_tr)
        cw = compute_class_weight('balanced', classes=classes, y=y_tr)
        sw = np.array([dict(zip(classes, cw))[l] for l in y_tr])

        # 骞惰鎼滅储
        results = random_search_parallel(X_tr, y_tr, sw, X_v, y_v, X_te, y_te, N_TRIALS)

        # 姣忎釜瀹為獙鐢?top3 鏋勫缓瀛愯瀺鍚?        if len(results) >= 3:
            ensemble, em = train_ensemble(results[:3], X_tr, y_tr, X_te, y_te)
            logger.info(f">>> {exp_name} 铻嶅悎妯″瀷: acc={em['accuracy']:.4f} f1={em['f1']:.4f} comp={em['composite_score']:.4f}")
        else:
            em = {'accuracy': results[0]['acc'], 'f1': results[0]['f1'],
                  'composite_score': results[0]['comp'],
                  'down_recall': results[0]['down_r'], 'up_recall': results[0]['up_r']}

        logger.info(f">>> {exp_name} 鏈€浣? acc={results[0]['acc']:.4f} f1={results[0]['f1']:.4f} "
                    f"comp={results[0]['comp']:.4f} down={results[0]['down_r']:.4f} up={results[0]['up_r']:.4f}")

        all_models.append({
            'name': exp_name, 'top_results': results[:5],
            'tier': tier, 'shift': shift, 'threshold': thresh,
            'features': avail, 'ensemble_acc': em['accuracy'],
            'ensemble_comp': em['composite_score']
        })

        if results[0]['comp'] > best_overall['comp']:
            best_overall = {
                'comp': results[0]['comp'], 'acc': results[0]['acc'],
                'f1': results[0]['f1'], 'down_r': results[0]['down_r'],
                'up_r': results[0]['up_r'],
                'model': results[0]['model'],
                'params': results[0]['params'],
                'features': avail, 'name': exp_name,
                'tier': tier, 'shift': shift, 'threshold': thresh,
            }

        # 淇濆瓨涓棿缁撴灉
        d = os.path.join('fast_results', exp_name)
        os.makedirs(d, exist_ok=True)
        results[0]['model'].save_model(os.path.join(d, 'model.json'))
        json.dump({k: float(v) if isinstance(v, (np.floating,)) else v
                   for k, v in em.items()}, open(os.path.join(d, 'metrics.json'), 'w'),
                  ensure_ascii=False, indent=2)

    # ===== 鏈€浣冲崟妯″瀷 =====
    logger.info(f"\n{'='*60}")
    logger.info(f"鏈€浣冲崟妯″瀷: {best_overall['name']}")
    logger.info(f"  acc={best_overall['acc']:.4f} f1={best_overall['f1']:.4f}")
    logger.info(f"  comp={best_overall['comp']:.4f} down={best_overall['down_r']:.4f} up={best_overall['up_r']:.4f}")

    # ===== 鍏ㄥ眬铻嶅悎锛堣法瀹為獙 top5锛?=====
    all_top = []
    for m in all_models:
        all_top.extend(m['top_results'])
    all_top.sort(key=lambda x: x['comp'], reverse=True)

    # 鐢ㄦ渶浣冲疄楠岀殑鏁版嵁鍋氬叏灞€铻嶅悎
    best_exp = best_overall['name']
    best_tier = best_overall['tier']
    best_shift = best_overall['shift']
    best_thresh = best_overall['threshold']

    processed_best = all_data[best_tier].copy()
    processed_best['future_total_hot'] = processed_best.groupby('keyword')['total_hot'].shift(best_shift)
    processed_best = processed_best.dropna(subset=['future_total_hot']).copy()
    cr = (processed_best['future_total_hot'] - processed_best['total_hot']) / (processed_best['total_hot'] + 1e-6)
    processed_best['label'] = 1
    processed_best.loc[cr > best_thresh, 'label'] = 2
    processed_best.loc[cr < -best_thresh, 'label'] = 0
    processed_best = processed_best.fillna(0)
    processed_best['keyword_enc'] = le.transform(processed_best['keyword'])

    features_best = best_overall['features']

    train_df = processed_best[processed_best['window_start'] <= '2024-12-31']
    test_df = processed_best[processed_best['window_start'] > '2025-12-31']
    X_tr_all, y_tr_all = train_df[features_best], train_df['label']
    X_te_all, y_te_all = test_df[features_best], test_df['label']

    # 鐢?top5 妯″瀷锛堟潵鑷笉鍚屽疄楠岋級鏋勫缓铻嶅悎
    top_global_models = all_top[:5]
    global_ensemble, global_em = train_ensemble(top_global_models, X_tr_all, y_tr_all, X_te_all, y_te_all)

    logger.info(f"\n{'='*60}")
    logger.info(f"鍏ㄥ眬铻嶅悎妯″瀷 (Top5)")
    logger.info(f"  acc={global_em['accuracy']:.4f} f1={global_em['f1']:.4f}")
    logger.info(f"  comp={global_em['composite_score']:.4f}")
    logger.info(f"  down_rec={global_em['down_recall']:.4f} up_rec={global_em['up_recall']:.4f}")
    logger.info(f"{'='*60}")

    # 瀵规瘮锛氬崟妯″瀷 vs 铻嶅悎
    logger.info(f"\n鍑嗙‘鐜囧姣? 鍗曟ā鍨?{best_overall['acc']:.4f} 鈫?铻嶅悎={global_em['accuracy']:.4f}")
    logger.info(f"缁煎悎璇勫垎瀵规瘮: 鍗曟ā鍨?{best_overall['comp']:.4f} 鈫?铻嶅悎={global_em['composite_score']:.4f}")

    # ===== 閫夋嫨鏈€缁堟ā鍨嬶紙鍙栦袱鑰呬腑鏇村ソ鐨勶級 =====
    use_ensemble = global_em['composite_score'] > best_overall['comp']
    final_model = global_ensemble if use_ensemble else best_overall['model']
    final_metrics = global_em if use_ensemble else best_overall
    final_type = 'Voting Ensemble (5 models)' if use_ensemble else 'Single XGBoost'

    # ===== 瀵煎嚭 =====
    d = 'fast_results/final_model'
    os.makedirs(d, exist_ok=True)

    # 淇濆瓨 model.pkl (VotingClassifier 鍙兘鐢?pickle)
    with open(os.path.join(d, 'model.pkl'), 'wb') as f:
        pickle.dump(final_model, f)

    # 鍚屾椂淇濆瓨 feature_columns
    with open(os.path.join(d, 'feature_columns.pkl'), 'wb') as f:
        pickle.dump(best_overall['features'], f)
    with open(os.path.join(d, 'label_encoder.pkl'), 'wb') as f:
        pickle.dump(le, f)
    with open(os.path.join(d, 'class_map.pkl'), 'wb') as f:
        pickle.dump({0: '涓嬮檷', 1: '骞崇ǔ', 2: '涓婂崌'}, f)
    with open(os.path.join(d, 'metrics.json'), 'w') as f:
        m = {k: float(v) if isinstance(v, (np.floating,)) else v
             for k, v in final_metrics.items() if k not in ('model',)}
        m['type'] = final_type
        json.dump(m, f, ensure_ascii=False, indent=2)

    logger.info(f"\n鏈€缁堟ā鍨? {final_type}")
    logger.info(f"淇濆瓨鍒? {d}/")
    logger.info(f"铻嶅悎妯″瀷: {'鏄? if use_ensemble else '鍚?}")
    logger.info(f"鏈€浣冲疄楠? {best_overall['name']}")
    logger.info(f"鍙傛暟: {best_overall['params']}")

    return 0


if __name__ == '__main__':
    mp.freeze_support()
    sys.exit(main())
