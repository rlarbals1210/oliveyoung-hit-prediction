import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from sklearn.model_selection import RepeatedStratifiedKFold, StratifiedKFold, cross_val_predict
from sklearn.metrics import roc_auc_score
import lightgbm as lgb
RS=42
f=pd.read_parquet('data/processed/features_v2.parquet')
TEXT=['evangelist_early_ratio','topic_shift','ad_ratio_2wk','voluntary_ratio_2wk','topic_diversity']
DROP=['product_id','category','launch_date_est','cutoff_date','price','price_original',
      'category_main','category_sub','brand','category_sub_group']
COLIN=['review_burst_3d','skin_type_n_unique']
for c in TEXT: f[c]=f[c].fillna(0)
f['rating_2wk_std']=f['rating_2wk_std'].fillna(0)
y=f['is_hit'].values
Xb=f.drop(columns=DROP+['is_hit']+TEXT).drop(columns=COLIN)
XC=pd.concat([Xb,f[TEXT]],axis=1)
# 신규 상호작용 피처
inter = (f['rating_2wk_std']*f['evangelist_early_ratio']).rename('std_x_evangelist')
XD=pd.concat([XC,inter],axis=1)   # 25피처
print("C=%d피처, D(+상호작용)=%d피처"%(XC.shape[1],XD.shape[1]))
def mk(): return lgb.LGBMClassifier(n_estimators=200,learning_rate=0.05,num_leaves=15,
    min_child_samples=10,random_state=RS,verbosity=-1)
rskf=RepeatedStratifiedKFold(n_splits=5,n_repeats=20,random_state=RS)
splits=list(rskf.split(XC,y))
def cv_auc(X):
    Xv=X.values; a=[]
    for tr,te in splits:
        m=mk(); m.fit(Xv[tr],y[tr]); a.append(roc_auc_score(y[te],m.predict_proba(Xv[te])[:,1]))
    return np.array(a)
aC=cv_auc(XC); aD=cv_auc(XD)
print("\nCV AUC: C(24) %.4f  D(25,+상호작용) %.4f  차이 %+.4f"%(aC.mean(),aD.mean(),aD.mean()-aC.mean()))
d=aD-aC; print("D>C fold 비율 %.0f%%  95%%구간 [%+.3f,%+.3f]"%(100*(d>0).mean(),*np.percentile(d,[2.5,97.5])))
# OOF 그룹별 — volatile 살아나나
skf=StratifiedKFold(n_splits=5,shuffle=True,random_state=RS)
def oof(X): return cross_val_predict(mk(),X.values,y,cv=skf,method='predict_proba')[:,1]
oC=oof(XC); oD=oof(XD)
m=f['rating_2wk_mean']; sd=f['rating_2wk_std']; dr=f['rating_drift'].fillna(0)
quiet=(m>=4.95)&(sd<=0.3)&(dr.abs()<=0.1); vol=(sd>=0.5)&(dr>0)
grp=np.where(quiet,'quiet',np.where(vol,'volatile','other'))
print("\n그룹별 OOF 평균 proba (C → D):")
for g in ['quiet','volatile','other']:
    mask=grp==g
    print("  %-9s n=%2d  hit%.0f%%   C %.3f → D %.3f  (%+.3f)"%(g,mask.sum(),100*y[mask].mean(),oC[mask].mean(),oD[mask].mean(),oD[mask].mean()-oC[mask].mean()))
print("\n전체 OOF AUC: C %.4f → D %.4f"%(roc_auc_score(y,oC),roc_auc_score(y,oD)))
# 프리메라 개별
i=np.where(f['product_id']=='A000000231293')[0]
if len(i): print("프리메라(분산형 대표) OOF: C %.3f → D %.3f"%(oC[i[0]],oD[i[0]]))
