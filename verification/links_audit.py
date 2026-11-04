from pathlib import Path
import sys,json,hashlib,time
import pandas as pd
ROOT=Path(__file__).parent;OUT=ROOT/'output';OUT.mkdir(exist_ok=True);CACHE=ROOT/'cache';sys.path.insert(0,str(ROOT/'input'));import verify_common_period as v
WB=str(ROOT/'input/DAO_apvienota_datu_kopa_A_B_kopigais_periods.xlsx')
def gql(q,var):
 p=CACHE/(hashlib.sha256(json.dumps([q,var],sort_keys=True).encode()).hexdigest()+'.json')
 if p.exists():return json.loads(p.read_text())
 d=orig(q,var,None,tries=3);p.write_text(json.dumps(d));time.sleep(.15);return d
orig=v.gql;v.gql=lambda q,var,key:gql(q,var)
b=pd.read_excel(WB,sheet_name='B_balsojumi_saskaņoti');out=[]
for start in range(0,len(b),100):
 batch=b.iloc[start:start+100];q='query($ids:[String!]){proposals(first:1000,where:{id_in:$ids}){id title created end votes state space{id}}}'
 try:
  ps=gql(q,{'ids':batch.iloc[:,2].tolist()})['proposals'];lookup={p['id']:p for p in ps}
  for _,r in batch.iterrows():
   p=lookup.get(r.iloc[2]);row=dict(space=r.iloc[1],id=r.iloc[2],found=p is not None)
   if p:
    stamp=pd.to_datetime(p['created'],unit='s',utc=True).strftime('%Y-%m-%d %H:%M'); actual_common=(v.C0<=p['end']<v.C1) if r.iloc[1]=='aavegotchi.eth' else (v.C0<=p['created']<v.C1)
    row.update(created_api=stamp,created_linked=r.iloc[5],link_status='END_RULE' if r.iloc[1]=='aavegotchi.eth' else ('OK' if stamp==r.iloc[5] else 'DIFFERS'),votes_api=p['votes'],votes_workbook=r.iloc[8],votes_status='OK' if p['votes']==r.iloc[8] else 'DIFFERS',window_api=actual_common,window_workbook=r.iloc[11],window_status='OK' if actual_common==r.iloc[11] else 'DIFFERS',space_status='OK' if p['space']['id']==r.iloc[1] else 'DIFFERS')
   out.append(row)
 except Exception as err:print('ERROR',start,str(err),flush=True)
 print('LINKS',start+len(batch),flush=True)
pd.DataFrame(out).to_csv(OUT/'B_links_vs_API.csv',index=False)
ex=pd.read_excel(WB,sheet_name='Izņemtie_kopīgais');rows=[]
for _,r in ex.iterrows():
 sp=r.iloc[1]
 try:
  info=gql('query($id:String!){space(id:$id){id name}}',{'id':sp})['space'];ps=[p for p in v.proposals(sp,v.C0,v.C1,None) if p['votes']>0]
  rows.append(dict(dao=r.iloc[0],space=sp,space_found=bool(info),live_proposals=len(ps),live_votes=sum(p['votes'] for p in ps),original_reason=r.iloc[3],status='NO_VOTES_CONFIRMED' if info and not ps else 'SPACE_NOT_FOUND' if not info else 'HAS_VOTES_REVIEW_REASON'))
 except Exception as err:rows.append(dict(dao=r.iloc[0],space=sp,status='ERROR',error=str(err)))
 print('EXCLUDED',sp,flush=True)
pd.DataFrame(rows).to_csv(OUT/'excluded_DAOs_vs_API.csv',index=False)
