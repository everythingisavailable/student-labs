"""Local-only API client and measured, reproducible Lab 5 experiment."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,json,os,platform,shutil,statistics,subprocess,threading,time
from urllib.parse import urlparse
import requests,psutil

ROOT=Path(__file__).resolve().parents[1]
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def csvsave(p,rows):
    if not rows:return
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with p.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})

def gpu():
    exe=shutil.which('nvidia-smi') or ('C:/Windows/System32/nvidia-smi.exe' if Path('C:/Windows/System32/nvidia-smi.exe').exists() else None)
    if not exe:return {'gpu_measurement':'unavailable'}
    try:
        s=subprocess.run([exe,'--query-gpu=name,memory.total,memory.used,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=4,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=True).stdout.strip().splitlines()[0].split(', ')
        return dict(gpu_name=s[0],vram_total_mib=float(s[1]),vram_used_mib=float(s[2]),gpu_percent=float(s[3]),gpu_measurement='nvidia-smi system-wide')
    except Exception as e:return {'gpu_measurement':'unavailable_'+type(e).__name__}

def snapshot():
    mem=psutil.virtual_memory()
    return dict(utc=datetime.now(timezone.utc).isoformat(),cpu_percent=psutil.cpu_percent(interval=.2),ram_used_gib=(mem.total-mem.available)/2**30,ram_available_gib=mem.available/2**30,ram_total_gib=mem.total/2**30,**gpu())

class Monitor:
    def __init__(self):self.stop=threading.Event();self.rows=[];self.thread=threading.Thread(target=self.loop,daemon=True)
    def loop(self):
        while not self.stop.is_set():
            row=snapshot();self.rows.append(row);self.stop.wait(.3)
    def __enter__(self):self.thread.start();return self
    def __exit__(self,*args):self.stop.set();self.thread.join(timeout=6)

def session():
    base=os.getenv('LOCAL_BASE_URL','http://localhost:1234').rstrip('/')
    if urlparse(base).hostname not in ['localhost','127.0.0.1','::1']:raise ValueError('Lab 5 requires a loopback API URL')
    s=requests.Session();s.trust_env=False
    if os.getenv('LOCAL_API_KEY'):s.headers['Authorization']='Bearer '+os.environ['LOCAL_API_KEY']
    return s,base

def ask(s,base,model,system,prompt,temp,limit,timeout):
    body=dict(model=model,messages=[dict(role='system',content=system),dict(role='user',content=prompt)],temperature=temp,max_tokens=limit,stream=False)
    with Monitor() as monitor:
        t=time.perf_counter()
        try:
            response=s.post(base+'/api/v0/chat/completions',json=body,timeout=timeout);response.raise_for_status();data=response.json();choice=data['choices'][0]
            result=dict(answer=choice['message'].get('content') or '',finish_reason=choice.get('finish_reason'),error=None,api_response=data)
        except Exception as e:result=dict(answer='',finish_reason=None,error=type(e).__name__,api_response=None)
        result['latency_s']=time.perf_counter()-t
    data=result['api_response'] or {};usage=data.get('usage') or {};stats=data.get('stats') or {};duration=stats.get('generation_time');tokens=usage.get('completion_tokens')
    result.update(input_tokens=usage.get('prompt_tokens'),output_tokens=tokens,generation_time_s=duration,server_tokens_per_second=stats.get('tokens_per_second'),computed_tokens_per_second=tokens/duration if tokens is not None and duration and duration>0 else None,server_ttft_s=stats.get('time_to_first_token'),system_samples=monitor.rows)
    return result

def summarize(run,rows,resources):
    save(run/'responses.json',rows);csvsave(run/'raw_results.csv',[{k:v for k,v in row.items() if k not in ['api_response','system_samples']} for row in rows])
    csvsave(run/'resource_samples.csv',[dict(test_id=r['id'],phase=r['phase'],repeat=r['repeat'],**sample) for r in rows for sample in r['system_samples']])
    bench=[r for r in rows if r['phase']=='benchmark'];csvsave(run/'benchmark.csv',[{k:r[k] for k in ['repeat','latency_s','input_tokens','output_tokens','generation_time_s','computed_tokens_per_second','server_tokens_per_second','server_ttft_s','error']} for r in bench])
    summary={'total_calls':len(rows),'errors':sum(bool(r['error']) for r in rows),'first_request_after_explicit_load_s':bench[0]['latency_s'],'mean_repeats_2_to_5_s':statistics.mean(r['latency_s'] for r in bench[1:]),'temperature':[],'resources':resources,'measurement_scope':'CPU/RAM and NVIDIA counters are system-wide, include other applications; first API request is after explicit load, not a cold load.'}
    for temp in sorted({r['temperature'] for r in rows if r['phase']=='temperature'}):
        rs=[r for r in rows if r['phase']=='temperature' and r['temperature']==temp]
        summary['temperature'].append(dict(temperature=temp,n=len(rs),unique_answers=len({r['answer'] for r in rs}),mean_latency_s=statistics.mean(r['latency_s'] for r in rs)))
    save(run/'summary.json',summary)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--experiment',action='store_true');ap.add_argument('--interactive',action='store_true');ap.add_argument('--prototype',action='store_true');ap.add_argument('--prompt');a=ap.parse_args()
    cfg=read(ROOT/'config.json');s,base=session();system=(ROOT/'prompts/system_lab01.txt').read_text(encoding='utf-8')
    if not a.experiment:
        if a.prototype:system=(ROOT/'prompts/prototype_lab03.txt').read_text(encoding='utf-8')
        if a.interactive:
            print('Локальный диалог. /exit — выход. Запросы независимы, история не передается.',flush=True)
            while True:
                try:prompt=input('Запрос: ')
                except EOFError:break
                if prompt=='/exit':break
                result=ask(s,base,cfg['model'],system,prompt,cfg['temperature'],cfg['max_tokens'],cfg['timeout_s']);print(result['answer'] or result['error'],flush=True)
        else:
            prompt=a.prompt or (ROOT/'data/prototype_event.txt').read_text(encoding='utf-8');print(ask(s,base,cfg['model'],system,prompt,cfg['temperature'],cfg['max_tokens'],cfg['timeout_s'])['answer'])
        return
    run=ROOT/'results'/datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_utc');run.mkdir(parents=True)
    for folder in ['src','prompts','data']:shutil.copytree(ROOT/folder,run/folder)
    shutil.copyfile(ROOT/'config.json',run/'config.json')
    models=s.get(base+'/api/v1/models',timeout=10);models.raise_for_status();models=models.json();save(run/'models_before.json',models)
    selected=next(x for x in models['models'] if x['key']==cfg['model'])
    print('RUN',run,flush=True)
    # Unload only the selected model for a real before-load baseline. No process is terminated.
    for instance in selected.get('loaded_instances',[]):
        response=s.post(base+'/api/v1/models/unload',json={'instance_id':instance['id']},timeout=120);response.raise_for_status()
    time.sleep(1)
    resources={'before_load':snapshot()};save(run/'resources.json',resources)
    t=time.perf_counter();loaded=s.post(base+'/api/v1/models/load',json={'model':cfg['model'],'context_length':cfg['context_length'],'echo_load_config':True},timeout=180);loaded.raise_for_status()
    save(run/'load.json',dict(client_load_s=time.perf_counter()-t,api_response=loaded.json()))
    resources['after_load']=snapshot();save(run/'resources.json',resources)
    metadata=dict(utc=datetime.now(timezone.utc).isoformat(),python=platform.python_version(),requests=requests.__version__,psutil=psutil.__version__,api_base=base,model=cfg['model'],seed=None,retries=0,scope='system-wide resource measurements',api_listeners=[dict(address=c.laddr.ip,port=c.laddr.port) for c in psutil.net_connections(kind='tcp') if c.status=='LISTEN' and c.laddr.port==1234])
    save(run/'metadata.json',metadata)
    jobs=[];tests=read(ROOT/'data/tests.json');previous=read(ROOT/'data/previous_prompts.json')
    for rep in range(1,6):jobs.append(dict(id='BENCH',phase='benchmark',repeat=rep,prompt=previous[0]['prompt'],system=system,temperature=.2))
    for test in previous:jobs.append(dict(id=test['id'],phase='previous_prompts',repeat=1,prompt=test['prompt'],system=system,temperature=.2))
    for test in tests:jobs.append(dict(id=test['id'],phase='required_examples',repeat=1,prompt=test['prompt'],system=system,temperature=.2))
    for temp in cfg['temperatures']:
        for rep in range(1,cfg['temperature_repeats']+1):jobs.append(dict(id='CREATIVE',phase='temperature',repeat=rep,prompt=(ROOT/'prompts/creative_lab02.txt').read_text(encoding='utf-8'),system=(ROOT/'prompts/creative_system_lab02.txt').read_text(encoding='utf-8'),temperature=temp))
    jobs.append(dict(id='INDIVIDUAL',phase='prototype',repeat=1,prompt=(ROOT/'data/prototype_event.txt').read_text(encoding='utf-8'),system=(ROOT/'prompts/prototype_lab03.txt').read_text(encoding='utf-8'),temperature=.2))
    rows=[]
    for job in jobs:
        result=ask(s,base,cfg['model'],job['system'],job['prompt'],job['temperature'],cfg['max_tokens'],cfg['timeout_s']);row={**job,**result};rows.append(row)
        with (run/'responses.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        print(job['phase'],job['id'],job['repeat'],job['temperature'],round(result['latency_s'],3),result['error'],flush=True)
    resources['after_experiment']=snapshot();save(run/'resources.json',resources);summarize(run,rows,resources)

if __name__=='__main__':main()
