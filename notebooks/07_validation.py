import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from sklearn.model_selection import RepeatedStratifiedKFold, StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import roc_auc_score
import lightgbm as lgb

RS=42
f=pd.read_parquet('data/processed/features_v2.parquet')
TEXT=['evangelist_early_ratio','topic_shift','ad_ratio_2wk','voluntary_ratio_2wk','topic_diversity']
DROP=['product_id','category','launch_date_est','cutoff_date','price','price_original',
      'category_main','category_sub','brand','category_sub_group']
COLIN=['review_burst_3d','skin_type_n_unique']
for c in TEXT: f[c]=f[c].fillna(0)
y=f['is_hit'].values
Xb=f.drop(columns=DROP+['is_hit']+TEXT).drop(columns=COLIN)
XA=Xb.copy(); XB=Xb.copy(); XC=pd.concat([Xb,f[TEXT]],axis=1)
print("피처 수: A/B=%d, C=%d, n=%d, hit=%d/non=%d"%(XB.shape[1],XC.shape[1],len(y),y.sum(),(1-y).sum()))

def mk_lgb(): return lgb.LGBMClassifier(n_estimators=200,learning_rate=0.05,num_leaves=15,
    min_child_samples=10,class_weight=None,random_state=RS,verbosity=-1)
def mk_logit(): return Pipeline([('s',StandardScaler()),('m',LogisticRegression(max_iter=1000,random_state=RS))])

models={'A 로지스틱(19)':(mk_logit,XA),'B LGBM(19)':(mk_lgb,XB),'C LGBM(24)':(mk_lgb,XC)}
rskf=RepeatedStratifiedKFold(n_splits=5,n_repeats=20,random_state=RS)
splits=list(rskf.split(XA,y))
print("\n=== RepeatedStratifiedKFold 5x20 = %d folds (각 test ~%d개) ==="%(len(splits),len(y)//5))
fold_auc={}
for name,(mk,X) in models.items():
    Xv=X.values; aucs=[]
    for tr,te in splits:
        m=mk(); m.fit(Xv[tr],y[tr]); p=m.predict_proba(Xv[te])[:,1]; aucs.append(roc_auc_score(y[te],p))
    aucs=np.array(aucs); fold_auc[name]=aucs
    lo,hi=np.percentile(aucs,[2.5,97.5])
    print("%-16s AUC 평균 %.4f  std %.3f  95%%구간 [%.3f, %.3f]"%(name,aucs.mean(),aucs.std(),lo,hi))

# 페어 비교: C-B per fold
d=fold_auc['C LGBM(24)']-fold_auc['B LGBM(19)']
dlo,dhi=np.percentile(d,[2.5,97.5])
print("\n[텍스트 효과] C-B fold별 차이: 평균 %+.4f  95%%구간 [%+.3f, %+.3f]  C>B 비율 %.0f%%"%(
    d.mean(),dlo,dhi,100*(d>0).mean()))
db=fold_auc['B LGBM(19)']-fold_auc['A 로지스틱(19)']
print("[모델 효과] B-A fold별 차이: 평균 %+.4f  B>A 비율 %.0f%%"%(db.mean(),100*(db>0).mean()))

# === OOF 에러분석 (C 모델) ===
print("\n=== OOF 예측 기반 2그룹 (train overlap 제거) ===")
skf=StratifiedKFold(n_splits=5,shuffle=True,random_state=RS)
oof=cross_val_predict(mk_lgb(),XC.values,y,cv=skf,method='predict_proba')[:,1]
f=f.assign(oof_proba=oof, pred=(oof>=0.5).astype(int))
m=f['rating_2wk_mean']; sd=f['rating_2wk_std'].fillna(0); dr=f['rating_drift'].fillna(0)
quiet=(m>=4.95)&(sd<=0.3)&(dr.abs()<=0.1)
volatile=(sd>=0.5)&(dr>0)
f['grp']=np.where(quiet,'quiet_perfect',np.where(volatile,'volatile','other'))
print("그룹       n   hit율   OOF평균proba  FN수(실제hit&pred0)")
for g in ['quiet_perfect','volatile','other']:
    s=f[f['grp']==g]
    fn=((s['is_hit']==1)&(s['pred']==0)).sum()
    print("%-12s %3d  %.1f%%   %.3f        %d"%(g,len(s),100*s['is_hit'].mean(),s['oof_proba'].mean(),fn))
print("\n전체 OOF AUC: %.4f"%roc_auc_score(y,oof))
# 4주차 FN 4개 OOF 추적
fn4={'A000000162114':'쏘내추럴픽서','A000000230208':'이니스프리레티놀',
     'A000000137964':'릴리바이레드','A000000231293':'프리메라'}
print("\n4주차 FN 4개 OOF proba / 그룹:")
for pid,nm in fn4.items():
    r=f[f['product_id']==pid]
    if len(r): print("  %-16s proba %.3f  grp %s  실제hit %d"%(nm,r['oof_proba'].iloc[0],r['grp'].iloc[0],r['is_hit'].iloc[0]))
