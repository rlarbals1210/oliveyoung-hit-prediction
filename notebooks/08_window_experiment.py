import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, sqlite3
con=sqlite3.connect('data/raw/oliveyoung.db')
rv=pd.read_sql("SELECT product_id,rating,content,written_at,has_photo,author_skin_type FROM reviews",con)
pr=pd.read_sql("SELECT product_id,launch_date_est FROM products",con)
con.close()
rv=rv.merge(pr,on='product_id')
rv['written_at']=pd.to_datetime(rv['written_at'],errors='coerce')
rv['launch']=pd.to_datetime(rv['launch_date_est'],errors='coerce')
rv=rv.dropna(subset=['written_at','launch'])
rv['dsl']=(rv['written_at']-rv['launch']).dt.days
rv['rlen']=rv['content'].fillna('').str.len()
# dedup (notebook 패턴)
rv=rv.drop_duplicates(['product_id','written_at','content','author_skin_type'])

def win_features(N):
    w=rv[(rv['dsl']>=0)&(rv['dsl']<N)].copy()
    g=w.groupby('product_id')
    out=pd.DataFrame({'product_id':[k for k in g.groups]}).set_index('product_id')
    out['count']=g.size()
    out['rmean']=g['rating'].mean(); out['rstd']=g['rating'].std()
    out['photo']=g['has_photo'].mean(); out['rlen']=g['rlen'].mean()
    # slope
    def slope(x):
        d=x['dsl'].value_counts().reindex(range(N),fill_value=0).sort_index()
        return np.polyfit(range(N),d.values,1)[0]
    out['slope']=g.apply(slope)
    # drift: first half(<N//2) vs second(>=N//2)
    h=N//2
    def drift(x):
        a=x.loc[x['dsl']<h,'rating']; b=x.loc[x['dsl']>=h,'rating']
        if len(a)==0 or len(b)==0: return np.nan
        return b.mean()-a.mean()
    out['drift']=g.apply(drift)
    return out

w14=win_features(14)
# 검증: 재계산 14일 vs 저장된 features_v2
f=pd.read_parquet('data/processed/features_v2.parquet').set_index('product_id')
chk=w14.join(f[['reviews_2wk_count','rating_2wk_mean','reviews_2wk_velocity_slope','rating_drift']],how='inner')
print("=== 14일 재현 검증 (재계산 vs 저장값 상관) ===")
print("count   corr %.3f"%chk['count'].corr(chk['reviews_2wk_count']))
print("rmean   corr %.3f"%chk['rmean'].corr(chk['rating_2wk_mean']))
print("slope   corr %.3f"%chk['slope'].corr(chk['reviews_2wk_velocity_slope']))
print("drift   corr %.3f"%chk['drift'].dropna().corr(chk['rating_drift']))

# === 모델 비교: 14 vs 21 vs 28 ===
from sklearn.model_selection import RepeatedStratifiedKFold, StratifiedKFold, cross_val_predict
from sklearn.metrics import roc_auc_score
import lightgbm as lgb
RS=42
TEXT=['evangelist_early_ratio','topic_shift','ad_ratio_2wk','voluntary_ratio_2wk','topic_diversity']
DROP=['category','launch_date_est','cutoff_date','price','price_original','category_main','category_sub','brand','category_sub_group']
COLIN=['review_burst_3d','skin_type_n_unique']
fr=pd.read_parquet('data/processed/features_v2.parquet').set_index('product_id')
for c in TEXT: fr[c]=fr[c].fillna(0)
y=fr['is_hit'].values
# 고정 그룹 (원래 14일 기준)
m0=fr['rating_2wk_mean']; s0=fr['rating_2wk_std'].fillna(0); d0=fr['rating_drift'].fillna(0)
quiet=((m0>=4.95)&(s0<=0.3)&(d0.abs()<=0.1)).values
vol=((s0>=0.5)&(d0>0)).values
WINCOLS={'reviews_2wk_count':'count','rating_2wk_mean':'rmean','rating_2wk_std':'rstd',
         'photo_review_ratio_2wk':'photo','review_length_mean_2wk':'rlen',
         'reviews_2wk_velocity_slope':'slope','rating_drift':'drift'}
def build(N):
    wf=win_features(N)
    g=fr.copy()
    for tgt,src in WINCOLS.items():
        g[tgt]=wf[src].reindex(g.index)
    g['rating_2wk_std']=g['rating_2wk_std'].fillna(0); g['rating_drift']=g['rating_drift'].fillna(0)
    X=g.drop(columns=DROP+['is_hit']+TEXT).drop(columns=COLIN)
    X=pd.concat([X,g[TEXT]],axis=1)
    return X
def mk(): return lgb.LGBMClassifier(n_estimators=200,learning_rate=0.05,num_leaves=15,min_child_samples=10,random_state=RS,verbosity=-1)
rskf=RepeatedStratifiedKFold(n_splits=5,n_repeats=20,random_state=RS); splits=list(rskf.split(np.zeros(len(y)),y))
skf=StratifiedKFold(n_splits=5,shuffle=True,random_state=RS)
print("\n=== 윈도우별 (고정 그룹, n=%d) ==="%len(y))
print("N일  CV평균AUC   전체OOF_AUC  quiet_OOF  volatile_OOF  other_OOF")
for N in [14,21,28]:
    X=build(N).values
    a=[roc_auc_score(y[te],mk().fit(X[tr],y[tr]).predict_proba(X[te])[:,1]) for tr,te in splits]
    oof=cross_val_predict(mk(),X,y,cv=skf,method='predict_proba')[:,1]
    print("%2d   %.4f      %.4f      %.3f      %.3f        %.3f"%(
        N,np.mean(a),roc_auc_score(y,oof),oof[quiet].mean(),oof[vol].mean(),oof[~quiet&~vol].mean()))
