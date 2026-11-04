from pathlib import Path
exec((Path(__file__).parent/'links_audit.py').read_text().split("b=pd.read_excel")[0])
from collections import Counter
A=pd.read_excel(WB,sheet_name='A_priekslikumi_logi');rows=[]
for sp,grp in A.groupby(A.columns[0]):
 try:
  ps=v.proposals(sp,int(grp.iloc[:,2].min()),int(grp.iloc[:,2].max())+1,None); c=Counter((int(p['created']),int(p['votes'])) for p in ps)
  for idx,r in grp.iterrows():
   k=(int(r.iloc[2]),int(r.iloc[3]));ok=c[k]>0
   if ok:c[k]-=1
   rows.append(dict(excel_row=idx+2,space=sp,created=k[0],votes=k[1],status='OK' if ok else 'NOT_MATCHED'))
 except Exception as err:rows.append(dict(space=sp,status='ERROR',error=str(err)))
 print('A_ROWS',sp,flush=True)
pd.DataFrame(rows).to_csv(OUT/'A_rows_vs_API.csv',index=False)
