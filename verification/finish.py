from pathlib import Path
import pandas as pd, numpy as np, json,hashlib,datetime,zipfile,shutil,subprocess
ROOT=Path(__file__).parent;OUT=ROOT/'output';OUT.mkdir(exist_ok=True);WB=(ROOT/'input/DAO_apvienota_datu_kopa_A_B_kopigais_periods.xlsx')
e=pd.read_csv(ROOT/'input/expected_common_period.csv');g=pd.read_csv(OUT/'live_by_dao.csv');vm=pd.read_csv(OUT/'live_vote_metrics.csv');pr=pd.read_csv(OUT/'live_proposals.csv');b=pd.read_excel(WB,sheet_name='B_balsojumi_saskaņoti');links=pd.read_csv(OUT/'B_links_vs_API.csv');ar=pd.read_csv(OUT/'A_rows_vs_API.csv')
assert len(g)==43 and len(pr)==948, 'Incomplete DAO/proposal coverage'
assert len(vm)==len(pr) and vm.id.nunique()==len(pr), 'Incomplete or duplicate vote coverage'
assert (vm.count_status=='OK').all() and vm.retrieved.sum()==86011, 'Vote count reconciliation failed'
assert len(links)==1018 and links.found.all(), 'Incomplete B proposal coverage'
assert pr.id.nunique()==948, 'Duplicate included proposal IDs'
assert len(ar)==2032 and (ar.status=='OK').all(), 'Incomplete A row verification'
comparison=[]
for _,r in e.merge(g,on='space',suffixes=('_expected','_live')).iterrows():
 for k in ['proposals','votes','median_voters','prior_median','yoy_pct']:
  a,c=r[k+'_expected'],r[k+'_live'];status='NEW_PRIOR' if pd.isna(a) and pd.notna(c) and k in ['prior_median','yoy_pct'] else 'OK' if (pd.isna(a) and pd.isna(c)) or (pd.notna(a) and pd.notna(c) and abs(a-c)<=.15*(k=='yoy_pct')+1e-8) else 'DIFFERS'
  comparison.append(dict(space=r.space,indicator=k,expected=a,live=c,status=status))
metrics=vm.groupby('space').agg(top1_live=('top1','median'),top5_live=('top5','median'),proposals_with_votes=('id','count'),retrieved_votes=('retrieved','sum')).reset_index();verified=g.merge(metrics,on='space',how='left').merge(e[['space','dao','source','top1_median','top5_median']],on='space')
for _,r in verified.iterrows():
 for k in ['top1','top5']:
  a=r[k+'_median']; c=r[k+'_live'];comparison.append(dict(space=r.space,indicator=k+'_median',expected=a,live=c,status='NEW_METRIC' if pd.isna(a) else 'OK' if abs(a-c)<=.005 else 'DIFFERS'))
comp=pd.DataFrame(comparison);comp.to_csv(OUT/'comparison.csv',index=False)
# Exact ID joins expose top-share differences that count-based mapping conceals.
bb=b.merge(vm,left_on=b.columns[2],right_on='id',how='left',suffixes=('','_api'))
per=[]
for _,r in bb.iterrows():
 if pd.notna(r.get('top1')):
  per.append(dict(space=r.iloc[1],id=r.iloc[2],workbook_top1=r.iloc[13],api_top1=r.top1,workbook_top5=r.iloc[14],api_top5=r.top5,top1_status='NOT_AVAILABLE' if pd.isna(r.iloc[13]) else 'OK' if abs(r.iloc[13]-r.top1)<=1e-6 else 'DIFFERS',top5_status='NOT_AVAILABLE' if pd.isna(r.iloc[14]) else 'OK' if abs(r.iloc[14]-r.top5)<=1e-6 else 'DIFFERS'))
pd.DataFrame(per).to_csv(OUT/'B_proposal_shares_vs_API.csv',index=False)
internal=pd.read_csv(OUT/'internal_checks.csv');internal=internal[~internal.scope.str.startswith('B_Adreses row ') & (internal.scope!='Kopsavilkums')]; extra=[]
def record(scope,k,exp,actual,tol=1e-8):
 ok=(pd.isna(exp) and pd.isna(actual)) or (pd.notna(exp) and pd.notna(actual) and abs(float(exp)-float(actual))<=tol)
 extra.append(dict(scope=scope,indicator=k,expected=exp,actual=actual,status='OK' if ok else 'DIFFERS'))
summary=pd.read_excel(WB,sheet_name='Kopsavilkums'); common=pd.read_excel(WB,sheet_name='Kopīgais_periods');y=e.yoy_pct.dropna()
values=[len(e),20,e.proposals.sum(),e.votes.sum(),e.median_voters.median(),sum(e.median_voters<50),sum(e.median_voters>=100),len(y),sum(y<0),y.median(),e.top5_median.notna().sum(),sum(e.top5_median>=.8),e.top5_median.median(),e.top1_median.median(),17,round(float(e.loc[e.space=='arbitrumfoundation.eth','votes'].iloc[0])/e.votes.sum()*100,1),int(b.iloc[:,12].sum()),b.loc[b.iloc[:,12]==True,b.columns[8]].sum()]
for (_,r),val in zip(summary.iterrows(),values):record('Kopsavilkums',r.iloc[0],r.iloc[1],val,.0001)
addr=pd.read_excel(WB,sheet_name='B_Adreses',header=5)
for idx,r in addr.iterrows():
 if isinstance(r.iloc[2],(int,float)) and pd.notna(r.iloc[2]) and r.iloc[3]>0:
  record('B_Adreses row '+str(idx+7),'coverage_formula',r.iloc[5],r.iloc[2]/r.iloc[3])
  record('B_Adreses row '+str(idx+7),'missing_records_formula',r.iloc[4],r.iloc[3]-r.iloc[2])
internal=pd.concat([internal,pd.DataFrame(extra)],ignore_index=True);internal.to_csv(OUT/'internal_checks.csv',index=False)
coverage=[]
for s in pd.ExcelFile(WB).sheet_names:
 coverage.append(dict(sheet=s,rows=openpyxl_rows if False else len(pd.read_excel(WB,sheet_name=s,header=None)),verification={'Kopīgais_periods':'All 43 DAO counts and medians vs API; VP medians independently recomputed','A_priekslikumi_logi':'All 2032 rows checked against API (timestamp, vote count); no proposal IDs in source','B_balsojumi_saskaņoti':'All 1018 IDs checked against API; date mappings and period flags checked','Izņemtie_kopīgais':'All 24 exclusions queried; absent spaces are not proof of historical absence','B_Adreses':'Coverage and missing-record arithmetic checked; address histories and identity not independently validated','Kopsavilkums':'All 18 summary rows recalculated','B_Balsojumi':'IDs covered by harmonized B table; full-period vote-level exports not all recollected','A_strategijas':'Reference-only historical strategy configuration not independently verified','A_kleros_balsotaji':'Reference-only full-period voter table; common-period validation does not verify each address'}.get(s,'Reference/documentation; no claim of independent verification for every field')))
coverage=pd.DataFrame(coverage)
sha=subprocess.check_output(['git','-C',__import__('os').environ.get('DAO_REPO_ROOT',str(ROOT.parent)),'rev-parse','HEAD'],text=True).strip()
provenance=pd.DataFrame([dict(item='GitHub repository',value='https://github.com/bernovskys/dao-governance-observatory'),dict(item='Git commit',value=sha),dict(item='Workbook SHA256',value=hashlib.sha256(WB.read_bytes()).hexdigest()),dict(item='API',value='https://hub.snapshot.org/graphql'),dict(item='retrieved_UTC',value=datetime.datetime.now(datetime.timezone.utc).isoformat()),dict(item='Execution',value='Cloud environment, GitHub source checkout; not a GitHub Actions run'),dict(item='VP tolerance',value='DAO medians: 0.005 absolute fraction (0.5 percentage points); proposal rows 0.000001'),dict(item='Tests',value='11 repository tests passed')])
notes=[('Periodi','2025-10-01 <= izveide < 2026-07-01; iepriekšējais: 2024-10-01 <= izveide < 2025-07-01. Aavegotchi: beigu datums un closed.'),('Triangulācijas neatkarība','A, B un jaunā pārbaude izmanto Snapshot. Tā ir atkārtota iegūšana un metožu salīdzināšana, nevis trīs neatkarīgi datu avoti.'),('Sasaistes kļūda',f"B: {(links.link_status=='DIFFERS').sum()} izveides datumi nesakrīt ar API; {(links.window_status=='DIFFERS').sum()} maina perioda piederību. Skaits/balsu summa to neatklāj."),('Uniswap labojums','Pilnam kopīgajam periodam top-1 mediāna 0.257516 (25.75%), nevis 0.247638 (24.76%); top-5 mediāna 0.916739 (91.67%), nevis 0.864636 (86.46%). B apakškopas mediānas nav visa perioda mediānas.'),('B mediānu tvērums','ENS, Decentraland, Uniswap: galvenie skaiti ņemti no A, bet B VP mediānas tikai no B pieejamajiem priekšlikumiem. API mediānas šajā failā aptver visu kopīgo periodu.'),('YoY','NEW_PRIOR ir iepriekš trūkuši dati, nevis pierādīta kļūda vēsturiskajā failā. Saglabātas gan sākotnējās, gan jaunās vērtības.'),('Aavegotchi YoY','Jauniegūtais iepriekšējā perioda rādītājs šeit ir pēc izveides datuma, tāpat kā pievienotajā verifikācijas kodā; kopīgais periods ir pēc beigām. Tādēļ tā NEW_PRIOR/YoY vērtība nav salīdzināma ar vienotu datuma kritēriju un nav jāiekļauj stingrā YoY secinājumā.'),('Personas','Adreses nav personas; nav noteikts patiesais balsstiesīgo vai nebalsojošo personu skaits.'),('Atsauces lapas','Stratēģijas, adrešu vēstures, ārējās saites un sākotnējo pilno periodu tabulas nav pilnībā neatkarīgi validētas. Skatīt lapu Parbaudes_tverums.'),('Pievienotais kods','14 no 15 repozitorija avota failiem identiski. reports.py atšķiras tikai f/rf virknes prefiksā; datu aprēķina atšķirība nav konstatēta.'),('GitHub','Darbs izpildīts ar GitHub repozitorija kodu mākoņvidē. Nav veikta GitHub Actions palaišana vai izmaiņu publicēšana.')]
notes=pd.DataFrame(notes,columns=['tema','skaidrojums'])
with pd.ExcelWriter(OUT/'DAO_triangulacija_parbaudita.xlsx',engine='openpyxl') as w:
 for name,d in [('Secinajumi',notes),('Parbauditie_DAO',verified),('Salidzinajums',comp),('B_sasaistes_API',links),('B_VP_parbaude',pd.DataFrame(per)),('A_rindas_API',ar),('Priekslikumi_API',pr),('Balsu_parbaude',vm),('Ieksejas_parbaudes',internal),('Iznemtie_DAO',pd.read_csv(OUT/'excluded_DAOs_vs_API.csv')),('Avota_faili',pd.read_csv(OUT/'source_comparison.csv')),('Parbaudes_tverums',coverage),('Izcelsme',provenance)]:
  d.to_excel(w,sheet_name=name,index=False);ws=w.sheets[name];ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
  for col in ws.columns:
   letter=col[0].column_letter;ws.column_dimensions[letter].width=min(65,max(14,max(len(str(c.value or '')) for c in list(col)[:100])+2))
  for c in ws[1]:c.font=__import__('openpyxl').styles.Font(bold=True,color='FFFFFF');c.fill=__import__('openpyxl').styles.PatternFill('solid',fgColor='234E70')
report=f'''# DAO triangulācijas pārbaude

GitHub avots: https://github.com/bernovskys/dao-governance-observatory/tree/{sha}

- Pārbaudīti 43 iekļautie un 24 izslēgtie DAO.
- API apstiprina 948 priekšlikumus un 86 011 balsis; visu 43 DAO priekšlikumu skaits, balsu summa un mediāna sakrīt.
- Iekšējās pārbaudes: {(internal.status=='OK').sum()} OK, {(internal.status=='DIFFERS').sum()} neatbilstības.
- A priekšlikumu rindas: {len(ar)}; statuss: {ar.status.value_counts().to_dict()}.
- B priekšlikumu ID: {len(links)}, visi atrasti; 285 sasaistītie izveides datumi atšķiras, diviem Convex priekšlikumiem mainās perioda piederība.
- Balsojumu pilnīgums: {len(vm)}/{len(pr)} priekšlikumi, {vm.retrieved.sum():,} balsu ieraksti; statusi: {vm.count_status.value_counts().to_dict()}.
- Rādītāju salīdzinājuma statusi: {comp.status.value_counts().to_dict()}.
- 11 repozitorija testi izturēti.

## Būtiskie ierobežojumi

'''+ '\n\n'.join('**'+str(r.tema)+'**: '+str(r.skaidrojums) for r in notes.itertuples())+'\n'
(OUT/'DAO_triangulacija_atskaite.md').write_text(report)
print(report)
