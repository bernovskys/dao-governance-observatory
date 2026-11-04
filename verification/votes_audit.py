from pathlib import Path
import sys,json,hashlib,time,statistics
import pandas as pd
ROOT=Path(__file__).parent;OUT=ROOT/'output';OUT.mkdir(exist_ok=True);CACHE=ROOT/'cache';sys.path.insert(0,str(ROOT/'input'))
import verify_common_period as v
def gql(q,var):
 p=CACHE/(hashlib.sha256(json.dumps([q,var],sort_keys=True).encode()).hexdigest()+'.json')
 if p.exists():return json.loads(p.read_text())

 for attempt in range(5):
  try:
   d=v.gql(q,var,None,tries=1);p.write_text(json.dumps(d));time.sleep(.8);return d
  except Exception as err:
   if '429' not in str(err) or attempt==4:raise
   print('RATE_LIMIT_WAIT_30S',flush=True);time.sleep(30)
props=pd.read_csv(OUT/'live_proposals.csv').to_dict('records'); rows=[]; errors=[]
def process(start):
 rows=[];errors=[]
 batch=props[start:start+2];print('VOTES',start+1,'/',len(props),flush=True)
 try:
  q='{'+''.join('p%d:votes(first:1000,skip:0,orderBy:"created",orderDirection:asc,where:{proposal:%s}){id vp}'%(i,json.dumps(p['id'])) for i,p in enumerate(batch))+'}'
  data=gql(q,{})
  for i,p in enumerate(batch):
   vs=data['p'+str(i)];offset=len(vs)
   while len(vs)>=offset and offset and offset%1000==0:
    q='{votes(first:1000,skip:%d,orderBy:"created",orderDirection:asc,where:{proposal:%s}){id vp}}'%(offset,json.dumps(p['id']))
    page=gql(q,{})['votes'];vs+=page
    if len(page)<1000:break
    offset+=1000
   uniq={z['id']:z for z in vs}; vp=sorted([float(z['vp'] or 0) for z in uniq.values() if float(z['vp'] or 0)>0],reverse=True);total=sum(vp)
   rows.append(dict(space=p['space'],id=p['id'],expected_count=p['votes'],retrieved=len(uniq),count_status='OK' if len(uniq)==p['votes'] else 'DIFFERS',top1=vp[0]/total if total else None,top5=sum(vp[:5])/total if total else None,vp_total=total))
 except Exception as e:errors.append(dict(start=start,error=str(e)));print('ERROR',str(e),flush=True)
 return rows,errors
from concurrent.futures import ThreadPoolExecutor,as_completed
with ThreadPoolExecutor(max_workers=1) as pool:
 for future in as_completed([pool.submit(process,i) for i in range(0,len(props),2)]):
  r,e=future.result();rows.extend(r);errors.extend(e)
  pd.DataFrame(rows).to_csv(OUT/'live_vote_metrics.csv',index=False);pd.DataFrame(errors).to_csv(OUT/'vote_errors.csv',index=False)
print('VOTES_COMPLETE',len(rows),flush=True)
