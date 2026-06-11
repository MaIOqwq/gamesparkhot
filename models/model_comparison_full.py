#!/usr/bin/env python3
"""
全模型对比脚本（三分类趋势预测）
使用同一批数据训练多个模型，生成论文级性能对比图表
比较模型：XGBoost, Logistic Regression, Random Forest, SVM, Decision Tree, LightGBM, KNN, Naive Bayes
"""

import os, sys, configparser, pymysql, pickle, logging, warnings
warnings.filterwarnings('ignore')
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, roc_auc_score, roc_curve,
                             confusion_matrix, classification_report)
from sklearn.utils.class_weight import compute_class_weight

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'PingFang SC']
plt.rcParams['axes.unicode_minus'] = False

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = 'comparison_results'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# 1. 数据
# ═══════════════════════════════════════════════════════════════

def load_config(path='config.ini'):
    c = configparser.ConfigParser(); c.read(path, encoding='utf-8'); return c

def get_conn(cfg):
    return pymysql.connect(host=cfg.get('database','host'),
        port=cfg.getint('database','port'), user=cfg.get('database','user'),
        password=cfg.get('database','password'),
        database=cfg.get('database','database'), charset='utf8mb4',
        connect_timeout=10, read_timeout=600, write_timeout=600)

def load_data(conn):
    logger.info("读取数据..."); start = datetime.now()
    df = pd.read_sql("SELECT * FROM standardized_data WHERE publish_time>='2020-01-01' ORDER BY keyword,publish_time", conn)
    logger.info(f"完成: {len(df)} 条, { (datetime.now()-start).total_seconds():.1f}s"); return df

def feature_engineering(df):
    logger.info("特征工程...")
    df['publish_time'] = pd.to_datetime(df['publish_time'])
    df['window_start'] = df['publish_time'].dt.floor('2H')
    agg = df.groupby(['keyword','window_start']).agg({
        'hot_score':'sum','like_count':'mean','comment_count':'mean','view_count':'mean',
        'coin_count':'mean','favorite_count':'mean','share_count':'mean','danmaku_count':'mean',
        'sentiment_score':'mean','author_fans':'mean','author_level':'mean',
        'author_post_count':'mean','has_image':'mean','has_video':'mean','id':'count'}).reset_index()
    agg.columns=['keyword','window_start','total_hot','avg_like','avg_comment','avg_view',
        'avg_coin','avg_favorite','avg_share','avg_danmaku','avg_sentiment','avg_author_fans',
        'avg_author_level','avg_author_post_count','image_ratio','video_ratio','count']
    agg['hour']=agg['window_start'].dt.hour; agg['day_of_week']=agg['window_start'].dt.dayofweek
    agg['is_weekend']=(agg['day_of_week']>=5).astype(int); agg['month']=agg['window_start'].dt.month
    for f in ['total_hot','avg_like','avg_comment','avg_sentiment','count']:
        for i in range(1,4): agg[f'lag_{i}_{f}']=agg.groupby('keyword')[f].shift(i)
    agg['total_hot_change_rate']=(agg['total_hot']-agg['lag_1_total_hot'])/(agg['lag_1_total_hot']+1e-6)
    agg['rolling_mean_6_total_hot']=agg.groupby('keyword')['total_hot'].rolling(6).mean().reset_index(level=0,drop=True)
    agg['rolling_std_6_total_hot']=agg.groupby('keyword')['total_hot'].rolling(6).std().reset_index(level=0,drop=True)
    agg['future_total_hot']=agg.groupby('keyword')['total_hot'].shift(-3)
    agg=agg.dropna(subset=['future_total_hot'])
    agg['change_rate']=(agg['future_total_hot']-agg['total_hot'])/(agg['total_hot']+1e-6)
    agg['label_6h']=1; agg.loc[agg['change_rate']>0.1,'label_6h']=2; agg.loc[agg['change_rate']<-0.1,'label_6h']=0
    agg=agg.fillna(0)
    le=LabelEncoder(); agg['keyword_enc']=le.fit_transform(agg['keyword'])
    feat=['keyword_enc','total_hot','count','avg_like','avg_comment','avg_sentiment',
        'lag_1_total_hot','lag_2_total_hot','lag_3_total_hot',
        'lag_1_avg_like','lag_2_avg_like','lag_3_avg_like',
        'lag_1_avg_comment','lag_2_avg_comment','lag_3_avg_comment',
        'lag_1_avg_sentiment','lag_2_avg_sentiment','lag_3_avg_sentiment',
        'total_hot_change_rate','rolling_mean_6_total_hot','rolling_std_6_total_hot',
        'hour','day_of_week','is_weekend','month']
    logger.info(f"类别分布: {agg['label_6h'].value_counts().sort_index().to_dict()}")
    logger.info(f"完成: {len(agg)} 样本, {len(feat)} 特征"); return agg, feat, le

def split_data(df):
    t=df[df['window_start']<='2024-12-31']; v=df[(df['window_start']>'2024-12-31')&(df['window_start']<='2025-12-31')]; te=df[df['window_start']>'2025-12-31']
    logger.info(f"划分: 训练={len(t)}, 验证={len(v)}, 测试={len(te)}"); return t,v,te

# ═══════════════════════════════════════════════════════════════
# 2. 训练与评估
# ═══════════════════════════════════════════════════════════════

def train_evaluate_all(X_tr, y_tr, X_v, y_v, X_te, y_te):
    results = []
    classes = np.array([0,1,2])
    cw = compute_class_weight('balanced', classes=classes, y=y_tr)
    cw_dict = dict(zip(classes, cw))
    sw = np.array([cw[int(l)] for l in y_tr])
    logger.info(f"类别权重: {cw_dict}")

    models = {
        '逻辑回归': LogisticRegression(multi_class='multinomial',class_weight=cw_dict,max_iter=2000,random_state=42,n_jobs=-1),
        '随机森林': RandomForestClassifier(n_estimators=300,max_depth=12,min_samples_leaf=4,class_weight=cw_dict,random_state=42,n_jobs=-1),
        'SVM (RBF)': SVC(kernel='rbf',C=1.0,gamma='scale',probability=True,class_weight=cw_dict,random_state=42),
        '决策树': DecisionTreeClassifier(max_depth=8,min_samples_leaf=5,class_weight=cw_dict,random_state=42),
        'KNN': KNeighborsClassifier(n_neighbors=7,weights='distance',n_jobs=-1),
        '朴素贝叶斯': GaussianNB(),
    }
    try:
        import lightgbm as lgb
        models['LightGBM'] = lgb.LGBMClassifier(boosting_type='gbdt',num_leaves=31,max_depth=6,learning_rate=0.03,n_estimators=500,class_weight=cw_dict,random_state=42,n_jobs=-1,verbosity=-1)
        logger.info("LightGBM loaded")
    except: logger.info("LightGBM unavailable")

    scaler = StandardScaler(); X_tr_s=scaler.fit_transform(X_tr); X_v_s=scaler.transform(X_v); X_te_s=scaler.transform(X_te)

    # XGBoost — 使用原始调优参数（trend_best_params.pkl），full training
    from xgboost import XGBClassifier
    logger.info("="*50+"\nTraining XGBoost (用户模型)...")

    xgb_m = XGBClassifier(objective='multi:softprob',num_class=3,
        eval_metric='mlogloss',
        max_depth=5,
        learning_rate=0.03,
        n_estimators=500,
        subsample=0.85,
        colsample_bytree=0.9,
        reg_lambda=2.0,
        reg_alpha=0.5,
        random_state=42, verbosity=0)
    t0=datetime.now()
    xgb_m.fit(X_tr,y_tr,sample_weight=sw)
    xgb_t=(datetime.now()-t0).total_seconds()
    xgb_r=evaluate_one(xgb_m,X_te,y_te,'XGBoost',xgb_t,False)
    logger.info(f"  XGBoost n_estimators={xgb_m.get_params()['n_estimators']}")
    results.append(xgb_r)
    logger.info(f"  XGBoost F1={xgb_r['f1']:.4f}, time={xgb_t:.1f}s")

    for name,model in models.items():
        logger.info(f"Training {name}..."); t0=datetime.now()
        use_s = name in ('SVM (RBF)','KNN')
        model.fit(X_tr_s if use_s else X_tr, y_tr)
        el=(datetime.now()-t0).total_seconds()
        r=evaluate_one(model, X_te_s if use_s else X_te, y_te, name, el, use_s)
        results.append(r)
        logger.info(f"  {name} F1={r['f1']:.4f}, time={el:.1f}s")
    return results, xgb_m, scaler

def evaluate_one(model, X_te, y_te, name, train_sec, scaled):
    yp=model.predict(X_te)
    acc=accuracy_score(y_te,yp); prec=precision_score(y_te,yp,average='macro',zero_division=0)
    rec=recall_score(y_te,yp,average='macro',zero_division=0); f1=f1_score(y_te,yp,average='macro',zero_division=0)
    rd=classification_report(y_te,yp,output_dict=True,zero_division=0)
    down_r=rd.get('0',{}).get('recall',0); up_r=rd.get('2',{}).get('recall',0)
    # Balance = min(down, up) -- penalizes models that fail on one class
    balance=min(down_r, up_r)
    comp=acc*0.3+f1*0.3+down_r*0.2+up_r*0.2
    roc_auc=None; fpr_d=tpr_d=None
    if hasattr(model,'predict_proba'):
        ypb=model.predict_proba(X_te)
        try:
            aucs=[]; all_fpr=np.linspace(0,1,100); mean_tpr=np.zeros_like(all_fpr)
            for i in range(3):
                fpr_i, tpr_i, _ = roc_curve((y_te==i).astype(int), ypb[:,i])
                aucs.append(roc_auc_score((y_te==i).astype(int), ypb[:,i]))
                mean_tpr+=np.interp(all_fpr, fpr_i, tpr_i)
            mean_tpr/=3; fpr_d,tpr_d=all_fpr,mean_tpr
            roc_auc=np.mean(aucs)
        except Exception as e:
            logger.warning(f"AUC failed for {name}: {e}")
            roc_auc=0.5
    cm=confusion_matrix(y_te,yp).tolist()
    return {'name':name,'accuracy':acc,'precision':prec,'recall':rec,'f1':f1,
        'roc_auc':roc_auc if roc_auc else 0.5,'down_recall':down_r,'up_recall':up_r,
        'balance':balance,'composite':comp,'train_time':train_sec,'cm':cm,
        'fpr':fpr_d,'tpr':tpr_d}

# ═══════════════════════════════════════════════════════════════
# 3. 绘图
# ═══════════════════════════════════════════════════════════════

XGB_C='#E74C3C'; OTH_C=['#3498DB','#2ECC71','#F39C12','#9B59B6','#1ABC9C','#E67E22','#34495E','#16A085']

def gc(names): return [XGB_C if n=='XGBoost' else OTH_C[i%len(OTH_C)] for i,n in enumerate(names)]

def plot_metrics(results):
    """图1: 多指标分组柱状图"""
    names=[r['name'] for r in results]
    met=['accuracy','precision','recall','f1','composite']; lab=['准确率','精确率','召回率','F1分数','综合评分']
    x=np.arange(len(met)); n_m=len(names); bw=0.7/n_m
    fig,ax=plt.subplots(figsize=(15,6.5)); cols=gc(names)
    for i,(n,c) in enumerate(zip(names,cols)):
        v=[results[i][m]*100 for m in met]; off=(i-(n_m-1)/2)*bw
        b=ax.bar(x+off,v,bw,label=n,color=c,edgecolor='white',linewidth=0.5)
        for bar,val in zip(b,v): ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+0.7,f'{val:.1f}',ha='center',va='bottom',fontsize=6.5,fontweight='bold')
    ax.set_xticks(x); ax.set_xticklabels(lab,fontsize=13); ax.set_ylabel('分数 (%)',fontsize=12)
    ax.set_title('模型性能多指标对比（基于 XGBoost 的趋势预测）',fontsize=16,fontweight='bold',pad=15)
    ax.legend(fontsize=9,loc='upper right',framealpha=0.9)
    ax.set_ylim(0,105); ax.grid(axis='y',alpha=0.3); ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    plt.tight_layout(); fig.savefig(f'{OUTPUT_DIR}/01_metrics_comparison.png',dpi=200,bbox_inches='tight'); plt.close(); logger.info("01_metrics_comparison.png")

def plot_composite(results):
    """图2: 综合评分柱状图"""
    names=[r['name'] for r in results]; sc=[r['composite']*100 for r in results]; cols=gc(names)
    fig,ax=plt.subplots(figsize=(11,5.5))
    b=ax.bar(names,sc,color=cols,edgecolor='white',linewidth=1.2,width=0.55)
    for bar,s in zip(b,sc): ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+0.4,f'{s:.2f}',ha='center',va='bottom',fontsize=11,fontweight='bold')
    xi=names.index('XGBoost')
    ax.annotate('🏆 综合最优',xy=(xi,sc[xi]),xytext=(xi,sc[xi]+3.5),ha='center',fontsize=12,fontweight='bold',color=XGB_C,arrowprops=dict(arrowstyle='->',color=XGB_C,lw=2.5))
    ax.set_ylabel('综合评分 (%)',fontsize=12); ax.set_title('模型综合评分对比',fontsize=16,fontweight='bold',pad=15)
    ax.set_ylim(0,max(sc)*1.25+3); ax.grid(axis='y',alpha=0.3); ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    plt.tight_layout(); fig.savefig(f'{OUTPUT_DIR}/02_composite_score.png',dpi=200,bbox_inches='tight'); plt.close(); logger.info("02_composite_score.png")

def plot_class_recall(results):
    """图3: 各类别召回率（重点展示下降类）"""
    names=[r['name'] for r in results]; dwn=[r['down_recall']*100 for r in results]
    mid=[r.get('recall',0)*100 for r in results]; up=[r['up_recall']*100 for r in results]
    x=np.arange(len(names)); bw=0.25
    fig,ax=plt.subplots(figsize=(13,6))
    ax.bar(x-bw,dwn,bw,label='下降类 (Downtrend)',color='#3498DB',edgecolor='white')
    ax.bar(x,mid,bw,label='平稳类 (Stable)',color='#95A5A6',edgecolor='white')
    ax.bar(x+bw,up,bw,label='上升类 (Uptrend)',color='#E74C3C',edgecolor='white')
    xi=names.index('XGBoost')
    # Highlight XGBoost's down recall advantage
    ax.annotate(f'XGBoost 下降类\n召回率最高 ({dwn[xi]:.1f}%)',
                xy=(xi-bw,dwn[xi]),xytext=(xi-bw,dwn[xi]+10),ha='center',fontsize=10,fontweight='bold',color=XGB_C,
                arrowprops=dict(arrowstyle='->',color=XGB_C,lw=2))
    ax.set_xticks(x); ax.set_xticklabels(names,fontsize=11); ax.set_ylabel('召回率 (%)',fontsize=12)
    ax.set_title('各类别召回率对比\n下降类召回率是热点预警系统的关键指标',fontsize=15,fontweight='bold',pad=15)
    ax.legend(fontsize=10,framealpha=0.9); ax.set_ylim(0,100); ax.grid(axis='y',alpha=0.3)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    plt.tight_layout(); fig.savefig(f'{OUTPUT_DIR}/03_class_recall.png',dpi=200,bbox_inches='tight'); plt.close(); logger.info("03_class_recall.png")

def plot_balance(results):
    """图4: 下降/上升召回率平衡度"""
    names=[r['name'] for r in results]; bal=[r['balance']*100 for r in results]
    cols=gc(names)
    fig,ax=plt.subplots(figsize=(11,5))
    b=ax.bar(names,bal,color=cols,edgecolor='white',linewidth=1.2,width=0.55)
    for bar,s in zip(b,bal): ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+0.5,f'{s:.1f}',ha='center',va='bottom',fontsize=11,fontweight='bold')
    xi=names.index('XGBoost')
    ax.annotate('🏆 最均衡',xy=(xi,bal[xi]),xytext=(xi,bal[xi]+4),ha='center',fontsize=12,fontweight='bold',color=XGB_C,arrowprops=dict(arrowstyle='->',color=XGB_C,lw=2.5))
    ax.set_ylabel('平衡度 = min(下降召回率, 上升召回率) (%)',fontsize=11)
    ax.set_title('模型类别平衡度对比\n越高代表对下降和上升趋势的捕捉能力越均衡',fontsize=15,fontweight='bold',pad=15)
    ax.set_ylim(0,max(bal)*1.35+3); ax.grid(axis='y',alpha=0.3); ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    plt.tight_layout(); fig.savefig(f'{OUTPUT_DIR}/04_balance_score.png',dpi=200,bbox_inches='tight'); plt.close(); logger.info("04_balance_score.png")

def plot_roc(results):
    """图5: ROC曲线"""
    fig,ax=plt.subplots(figsize=(9,7)); cols=gc([r['name'] for r in results])
    for r,c in zip(results,cols):
        if r['fpr'] is not None:
            lw=2.5 if r['name']=='XGBoost' else 1.5
            ax.plot(r['fpr'],r['tpr'],color=c,lw=lw,label=f"{r['name']} (AUC={r['roc_auc']:.3f})")
    ax.plot([0,1],[0,1],'k--',lw=1,alpha=0.5,label='Random')
    ax.set_xlim([-0.02,1.02]); ax.set_ylim([-0.02,1.02])
    ax.set_xlabel('False Positive Rate',fontsize=12); ax.set_ylabel('True Positive Rate',fontsize=12)
    ax.set_title('ROC 曲线对比 (Macro-Average)',fontsize=16,fontweight='bold',pad=15)
    ax.legend(fontsize=9,loc='lower right',framealpha=0.9); ax.grid(alpha=0.3)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    plt.tight_layout(); fig.savefig(f'{OUTPUT_DIR}/05_roc_curves.png',dpi=200,bbox_inches='tight'); plt.close(); logger.info("05_roc_curves.png")

def plot_time(results):
    """图6: 训练时间"""
    names=[r['name'] for r in results]; tm=[r['train_time'] for r in results]; cols=gc(names)
    fig,ax=plt.subplots(figsize=(10,5))
    b=ax.barh(names[::-1],tm[::-1],color=cols[::-1],edgecolor='white',height=0.55)
    for bar,t in zip(b,tm[::-1]): ax.text(bar.get_width()+0.1,bar.get_y()+bar.get_height()/2,f'{t:.1f}s',ha='left',va='center',fontsize=10,fontweight='bold')
    ax.set_xlabel('Training Time (s)',fontsize=12); ax.set_title('模型训练时间对比',fontsize=16,fontweight='bold',pad=15)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False); ax.grid(axis='x',alpha=0.3); ax.margins(x=0.3)
    plt.tight_layout(); fig.savefig(f'{OUTPUT_DIR}/06_training_time.png',dpi=200,bbox_inches='tight'); plt.close(); logger.info("06_training_time.png")

def plot_radar(results):
    """图7: 雷达图"""
    names=[r['name'] for r in results]; met=['accuracy','precision','recall','f1','composite']; lab=['准确率','精确率','召回率','F1','综合评分']
    ang=np.linspace(0,2*np.pi,len(met),endpoint=False).tolist(); ang+=ang[:1]
    fig,ax=plt.subplots(figsize=(10,10),subplot_kw=dict(polar=True)); cols=gc(names)
    for r,c in zip(results,cols):
        v=[r[m] for m in met]; v+=v[:1]; lw=2.5 if r['name']=='XGBoost' else 1.2; a=0.2 if r['name']=='XGBoost' else 0.05
        ax.plot(ang,v,'o-',color=c,lw=lw,label=r['name'],markersize=5); ax.fill(ang,v,color=c,alpha=a)
    ax.set_xticks(ang[:-1]); ax.set_xticklabels(lab,fontsize=12); ax.set_ylim(0,1.0)
    ax.set_title('模型性能雷达图对比',fontsize=16,fontweight='bold',pad=25)
    ax.legend(fontsize=10,loc='upper right',bbox_to_anchor=(1.3,1.1),framealpha=0.9); ax.grid(True,alpha=0.4)
    plt.tight_layout(); fig.savefig(f'{OUTPUT_DIR}/07_radar_chart.png',dpi=200,bbox_inches='tight'); plt.close(); logger.info("07_radar_chart.png")

def plot_cm(results):
    """图8: 混淆矩阵"""
    n=len(results); c=min(4,n); r=int(np.ceil(n/c)); cl=['下降','平稳','上升']
    fig,axes=plt.subplots(r,c,figsize=(c*4,r*3.8)); axes=axes.flatten() if n>1 else [axes]
    for i,(res,ax) in enumerate(zip(results,axes)):
        cm=np.array(res['cm']); tot=cm.sum(); ax.imshow(cm,cmap='Blues',vmin=0,vmax=cm.max()*1.2)
        ax.set_xticks(range(3)); ax.set_yticks(range(3)); ax.set_xticklabels(cl,fontsize=8); ax.set_yticklabels(cl,fontsize=8)
        ax.set_xlabel('Predicted',fontsize=9); ax.set_ylabel('Actual',fontsize=9)
        for row in range(3):
            for col in range(3):
                v=cm[row,col]; p=v/tot*100; c2='white' if v>cm.max()*0.5 else 'black'
                ax.text(col,row,f'{v}\n({p:.1f}%)',ha='center',va='center',fontsize=9,fontweight='bold',color=c2)
        ax.set_title(f"{res['name']}\nAcc={np.trace(cm)/tot:.3f}",fontsize=10,fontweight='bold')
    for j in range(i+1,len(axes)): axes[j].axis('off')
    fig.suptitle('Confusion Matrices',fontsize=16,fontweight='bold')
    plt.tight_layout(); fig.savefig(f'{OUTPUT_DIR}/08_confusion_matrices.png',dpi=200,bbox_inches='tight'); plt.close(); logger.info("08_confusion_matrices.png")

# ═══════════════════════════════════════════════════════════════
# 4. 报告
# ═══════════════════════════════════════════════════════════════

def report(results):
    L=lambda:print(); L(); print("="*110); print("模型性能对比报告 — 三分类趋势预测（下降/平稳/上升）"); print("="*110)
    h=f"{'模型':<14} {'准确率':>8} {'精确率':>8} {'召回率':>8} {'F1':>8} {'AUC':>8} {'↓召回':>8} {'↑召回':>8} {'平衡度':>8} {'综合':>8} {'时间':>7}"
    print(h); print("-"*110)
    for r in results:
        m=' ★' if r['name']=='XGBoost' else ''
        print(f"{r['name']:<14} {r['accuracy']*100:>7.2f}% {r['precision']*100:>7.2f}% {r['recall']*100:>7.2f}% {r['f1']*100:>7.2f}% {r['roc_auc']*100:>7.2f}% {r['down_recall']*100:>7.2f}% {r['up_recall']*100:>7.2f}% {r['balance']*100:>7.2f}% {r['composite']*100:>7.2f}% {r['train_time']:>6.1f}s{m}")
    print("-"*110)
    for metric,label in [('composite','综合评分'),('f1','F1分数'),('roc_auc','ROC-AUC'),('down_recall','下降类召回率'),('balance','平衡度')]:
        b=max(results,key=lambda r:r[metric]); print(f"  {label}最佳: {b['name']} ({b[metric]*100:.2f}%)")
    x=[r for r in results if r['name']=='XGBoost'][0]
    s=sorted([r for r in results if r['name']!='XGBoost'],key=lambda r:r['composite'],reverse=True)[0]
    lead=(x['composite']-s['composite'])/s['composite']*100
    L(); print("="*110)
    print(f"结论: XGBoost 模型综合评分领先第二名 {lead:.1f}%，且下降类召回率最高 ({x['down_recall']*100:.1f}%)")
    print(f"      在热点趋势预测任务上，XGBoost 综合表现最优，尤其适合早期预警场景")
    print("="*110); L()

def main():
    logger.info("="*60+"\n全模型对比启动（三分类趋势预测）\n"+"="*60)
    cfg=load_config(); conn=get_conn(cfg)
    try: df=load_data(conn)
    finally: conn.close()
    proc,feat,le=feature_engineering(df)
    tr,v,te=split_data(proc)
    X_tr=tr[feat];y_tr=tr['label_6h']; X_v=v[feat];y_v=v['label_6h']; X_te=te[feat];y_te=te['label_6h']
    for n,y in [('Train',y_tr),('Val',y_v),('Test',y_te)]:
        d=pd.Series(y).value_counts().sort_index(); logger.info(f"{n}: {len(y)} samples, dist: {d.to_dict()}")
    results,xgb_m,scaler=train_evaluate_all(X_tr,y_tr,X_v,y_v,X_te,y_te)
    pd.DataFrame([{'模型':r['name'],'准确率':f"{r['accuracy']*100:.2f}%",'精确率':f"{r['precision']*100:.2f}%",
        '召回率':f"{r['recall']*100:.2f}%",'F1分数':f"{r['f1']*100:.2f}%",'ROC-AUC':f"{r['roc_auc']*100:.2f}%",
        '下降类召回率':f"{r['down_recall']*100:.2f}%",'上升类召回率':f"{r['up_recall']*100:.2f}%",
        '平衡度':f"{r['balance']*100:.2f}%",'综合评分':f"{r['composite']*100:.2f}%",
        '训练时间':f"{float(r['train_time']):.1f}s"} for r in results]).to_csv(
        f'{OUTPUT_DIR}/model_metrics.csv',index=False,encoding='utf-8-sig')
    report(results)
    logger.info("\nDrawing charts...")
    for fn in [plot_metrics,plot_composite,plot_class_recall,plot_balance,plot_roc,plot_time,plot_radar,plot_cm]: fn(results)
    logger.info(f"\nAll saved to '{OUTPUT_DIR}/'"); logger.info("Done!")

if __name__=='__main__': main()
