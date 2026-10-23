import argparse,json,threading,time,platform,hashlib,shutil,subprocess,urllib.error
from datetime import datetime,timezone
import psutil
from providers import ROOT,ask,settings,request
def snapshot():
 mem=psutil.virtual_memory();row=dict(utc=datetime.now(timezone.utc).isoformat(),cpu_percent=psutil.cpu_percent(interval=.2),ram_used_gib=(mem.total-mem.available)/2**30,ram_total_gib=mem.total/2**30)
 exe=shutil.which('nvidia-smi') or 'C:/Windows/System32/nvidia-smi.exe'
 try:
  raw=subprocess.run([exe,'--query-gpu=name,memory.total,memory.used,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,check=True,timeout=4,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).stdout.strip().splitlines()[0].split(', ')
  row.update(gpu=raw[0],vram_total_mib=float(raw[1]),vram_used_mib=float(raw[2]),gpu_percent=float(raw[3]))
 except Exception as exc:row['gpu_unavailable']=type(exc).__name__
 return row
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--backend',choices=['local','cloud'],required=True);a=ap.parse_args();cfg=settings()
 if a.backend=='cloud' and not cfg.get('GIGACHAT_AUTH_KEY' if cfg.get('CLOUD_PROVIDER')=='gigachat' else 'CLOUD_API_KEY'):raise SystemExit('Cloud key missing; no requests sent')
 if a.backend=='cloud':
  model=cfg.get('CLOUD_MODEL','')
  catalog_url=cfg['CLOUD_BASE_URL']+'/models'
  try:
   if cfg.get('CLOUD_PROVIDER')=='gigachat':
    from gigachat_provider import call
    catalog=call(cfg,'/models')['data'];balance=call(cfg,'/balance')
    remaining=next((x['value'] for x in balance['balance'] if x['usage']=='GigaChat'),0)
    if remaining<100000:raise SystemExit('Insufficient token allowance for the fixed experiment.')
   else:catalog=request('https://openrouter.ai/api/v1','/models')['data'];balance=None
  except urllib.error.HTTPError as exc:raise SystemExit('Cloud API preflight failed: HTTP '+str(exc.code)+'. No model requests sent.') from None
  except Exception as exc:raise SystemExit('Cloud API preflight failed: '+type(exc).__name__+'. No model requests sent.') from None
  entry=next((x for x in catalog if x['id']==model),None)
  if entry is None:raise SystemExit('Selected model is not in the current catalog; no requests sent.')
  if cfg.get('CLOUD_PROVIDER')!='gigachat' and any(float(entry['pricing'].get(k,0))!=0 for k in ['prompt','completion','request']):raise SystemExit('Model is not zero price')
 tests=json.loads((ROOT/'data/test_cases.json').read_text(encoding='utf-8'));plan=json.loads((ROOT/'data/experiment_plan.json').read_text(encoding='utf-8'));system=(ROOT/'data/system.txt').read_text(encoding='utf-8')
 assert hashlib.sha256((ROOT/'data/test_cases.json').read_bytes()).hexdigest()==plan['test_sha256']
 run=ROOT/'results'/(datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_utc')+'_'+a.backend);run.mkdir()
 if a.backend=='cloud':
  (run/'cloud_model_catalog_entry.json').write_text(json.dumps(dict(retrieved_at_utc=datetime.now(timezone.utc).isoformat(),source=catalog_url,model=entry,balance_before=balance),ensure_ascii=False,indent=2),encoding='utf-8')
 for name in ['src','data']:shutil.copytree(ROOT/name,run/name,ignore=shutil.ignore_patterns('__pycache__'))
 samples=[];stop=threading.Event()
 def monitor():
  while not stop.is_set():samples.append(snapshot());stop.wait(.8)
 t=threading.Thread(target=monitor,daemon=True);before=snapshot();t.start();started=time.perf_counter();rows=[]
 try:
  for test in tests:
   for rep in range(1,4 if test['id'] in plan['repeat_three_times'] else 2):
    r=ask(a.backend,test['prompt'],system);r.update(test_id=test['id'],repeat=rep,criterion=test['criterion']);rows.append(r)
    with (run/'raw_results.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    print(test['id'],rep,round(r['latency_s'],2),r['error'],flush=True)
    if a.backend=='cloud' and r['error']:raise SystemExit('Cloud request failed; run stopped. Existing results preserved; no automatic retries.')
    if a.backend=='cloud' and cfg.get('CLOUD_PROVIDER')!='gigachat':time.sleep(3.1)
 finally:
  elapsed=time.perf_counter()-started;stop.set();t.join(timeout=6)
  meta=dict(backend=a.backend,python=platform.python_version(),os=platform.platform(),logical_processors=psutil.cpu_count(),physical_cores=psutil.cpu_count(logical=False),before=before,samples=samples,scope='Whole local workstation including other programs; not cloud server resources. Local baseline is after model loading.',calls=len(rows),errors=sum(bool(r['error']) for r in rows),wall_s=elapsed,completed_requests_per_minute=sum(not r['error'] for r in rows)*60/elapsed,first_request_latency_s=rows[0]['latency_s'] if rows else None)
  (run/'environment_resources.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
 if a.backend=='cloud' and cfg.get('CLOUD_PROVIDER')=='gigachat':
  try:(run/'balance_after.json').write_text(json.dumps(call(cfg,'/balance'),ensure_ascii=False,indent=2),encoding='utf-8')
  except Exception:print('Post-run balance unavailable; raw results preserved.',flush=True)
 print('SAVED',run,flush=True)
if __name__=='__main__':main()
