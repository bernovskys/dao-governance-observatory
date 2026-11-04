from pathlib import Path
import sys,json,hashlib,time,datetime,csv,statistics,traceback
import pandas as pd
import openpyxl
sys.path.insert(0,str(Path(__file__).parent/'input'))
import verify_common_period as v
ROOT=Path(__file__).parent; OUT=ROOT/'output';OUT.mkdir(exist_ok=True); CACHE=ROOT/'cache'; CACHE.mkdir(exist_ok=True)
WB=(ROOT/'input/DAO_apvienota_datu_kopa_A_B_kopigais_periods.xlsx')
checks=[]
def check(scope,indicator,expected,actual,tol=1e-8,note=''):
 if pd.isna(expected) and pd.isna(actual): status='OK'
 elif pd.isna(expected) or pd.isna(actual): status='DIFFERS'
 elif isinstance(expected,(int,float)) and isinstance(actual,(int,float)): status='OK' if abs(expected-actual)<=tol else 'DIFFERS'
 else: status='OK' if expected==actual else 'DIFFERS'
 checks.append(dict(scope=scope,indicator=indicator,expected=expected,actual=actual,status=status,note=note))
x=pd.ExcelFile(WB); common=pd.read_excel(x,'Kopīgais_periods'); A=pd.read_excel(x,'A_priekslikumi_logi'); B=pd.read_excel(x,'B_balsojumi_saskaņoti'); excluded=pd.read_excel(x,'Izņemtie_kopīgais'); expected=pd.read_csv(ROOT/'input/expected_common_period.csv')
print('HEADERS',list(common.columns),flush=True)
for _,e in expected.iterrows():
 sp=e.space; r=common[common.iloc[:,1]==sp].iloc[0]; aa=A[(A.iloc[:,0]==sp)&(A.iloc[:,7]==True)]; bb=B[(B.iloc[:,1]==sp)&(B.iloc[:,12]==True)]
 for col,k in [(17,'proposals'),(18,'votes'),(19,'median_voters'),(7,'prior_median'),(8,'yoy_pct')]: check(sp,'Excel_vs_expected_'+k,e[k],r.iloc[col],0.000001)
 for label,d,vc,cols in [('A',aa,3,(4,5,6)),('B',bb,8,(9,10,11))]:
  if pd.notna(r.iloc[cols[0]]):
   vals=d.iloc[:,vc].tolist()
   for ci,actual in zip(cols,[len(vals),sum(vals),statistics.median(vals) if vals else None]): check(sp,f'{label}_raw_'+str(common.columns[ci]),r.iloc[ci],actual)
 if len(bb):
  for i,bc in [(12,13),(13,14)]: check(sp,'B_raw_'+str(common.columns[i]),r.iloc[i],bb.iloc[:,bc].median())
 prior=A[(A.iloc[:,0]==sp)&(A.iloc[:,5]==True)&(A.iloc[:,3]>0)]
 if pd.notna(e.prior_median): check(sp,'A_prior_raw_median',e.prior_median,prior.iloc[:,3].median())
 if pd.notna(e.prior_median) and e.prior_median>0: check(sp,'YoY_formula',e.yoy_pct,round(100*(e.median_voters/e.prior_median-1),1),0.00001)
check('ALL','DAO_count',43,len(common));check('ALL','proposal_total',948,common.iloc[:,17].sum());check('ALL','vote_total',86011,common.iloc[:,18].sum())
check('B','duplicate_proposal_IDs',0,int(B.iloc[:,2].duplicated().sum()))
check('A','duplicate_space_timestamp',0,int(A.duplicated(subset=[A.columns[0],A.columns[2]]).sum()),note='Same timestamp may be legitimate; requires proposal IDs')
pd.DataFrame(checks).to_csv(OUT/'internal_checks.csv',index=False)
# Compare every supplied source file with the checked-out GitHub revision.
mapping=json.loads((ROOT/'input/upload_mapping.json').read_text()); mapping={k:str(ROOT/p) for k,p in mapping.items()}
files=[]
for name,p in mapping.items():
 q=Path(__import__('os').environ.get('DAO_REPO_ROOT',str(ROOT.parent)))/name; raw=Path(p).read_bytes(); files.append(dict(file=name,uploaded_sha256=hashlib.sha256(raw).hexdigest(),github_sha256=hashlib.sha256(q.read_bytes()).hexdigest() if q.exists() else '',identical=q.exists() and raw==q.read_bytes()))
pd.DataFrame(files).to_csv(OUT/'source_comparison.csv',index=False)
orig=v.gql
def cached(query,variables,key):
 h=hashlib.sha256(json.dumps([query,variables],sort_keys=True).encode()).hexdigest(); p=CACHE/(h+'.json')
 if p.exists(): return json.loads(p.read_text())
 data=orig(query,variables,key,tries=3);p.write_text(json.dumps(data));time.sleep(.12);return data
v.gql=cached
live=[]; props=[]; failures=[]; exclusions=set(pd.read_csv(ROOT/'input/excluded_test_proposals.csv').proposal_id)
for idx,e in expected.iterrows():
 sp=e.space;print(f'LIVE {idx+1}/{len(expected)} {sp}',flush=True)
 try:
  # End-window selection has no arbitrary 90-day creation cutoff.
  ps=v.proposals(sp,0 if e.window_rule=='end' else v.C0,v.C1,None)
  if e.window_rule=='end': ps=[p for p in ps if v.C0<=p['end']<v.C1 and p['state']=='closed']
  use=[p for p in ps if p['votes']>0 and p['id'] not in exclusions]
  prior=[p for p in v.proposals(sp,v.Q0,v.Q1,None) if p['votes']>0 and p['id'] not in exclusions]
  vals=[p['votes'] for p in use]; pv=[p['votes'] for p in prior]; m=v.med(vals);pm=v.med(pv)
  live.append(dict(space=sp,proposals=len(use),votes=sum(vals),median_voters=m,prior_median=pm,yoy_pct=round(100*(m/pm-1),1) if m is not None and pm else None,window_rule=e.window_rule,open_proposals=sum(p['state']!='closed' for p in use)))
  for p in use: props.append(dict(space=sp,**p))
 except Exception as err: failures.append(dict(space=sp,error=str(err))); print('ERROR',sp,str(err),flush=True)
 pd.DataFrame(live).to_csv(OUT/'live_by_dao.csv',index=False);pd.DataFrame(props).to_csv(OUT/'live_proposals.csv',index=False);pd.DataFrame(failures).to_csv(OUT/'live_errors.csv',index=False)
print('METADATA_COMPLETE',len(live),len(props),flush=True)
