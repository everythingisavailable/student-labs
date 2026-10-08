"""Frozen benchmark, resumable raw records, strict format checks, no silent retries."""
from pathlib import Path
import argparse,collections,csv,datetime,hashlib,json,math,os,platform,re,shutil,statistics,time,urllib.request

ROOT=Path(__file__).resolve().parents[1]
FIELDS=('status','category','risk','evidence','missing_data','next_action')
CRITERIA=('factual_correctness','completeness','instruction_following','relevance')

def read(p): return json.loads(p.read_text(encoding='utf-8'))
def save(p,value): p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def csvsave(p,rows):
    if not rows:return
    with p.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader()
        for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})

def env():
    p=ROOT/'.env'
    if p.exists():
        for line in p.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k,v=line.split('=',1);os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
    return os.getenv('LLM_BASE_URL','http://localhost:1234/v1').rstrip('/'),os.getenv('LLM_API_KEY','lm-studio')

def call(system,user,model,temperature,max_tokens,timeout):
    base,key=env();body={'model':model,'messages':[{'role':'system','content':system},{'role':'user','content':user}],'temperature':temperature,'max_tokens':max_tokens,'stream':False}
    request=urllib.request.Request(base+'/chat/completions',json.dumps(body).encode(),{'Content-Type':'application/json','Authorization':'Bearer '+key})
    started=time.perf_counter()
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response:raw=json.load(response)
        choice=raw['choices'][0];message=choice['message'];usage=raw.get('usage') or {}
        return dict(raw=message.get('content') or '',reasoning=message.get('reasoning_content') or message.get('reasoning') or '',latency_s=time.perf_counter()-started,input_tokens=usage.get('prompt_tokens'),output_tokens=usage.get('completion_tokens'),finish_reason=choice.get('finish_reason'),returned_model=raw.get('model'),error=None,api_response=raw)
    except Exception as exc:
        # Do not persist headers, credentials, local paths or exception text.
        return dict(raw='',reasoning='',latency_s=time.perf_counter()-started,input_tokens=None,output_tokens=None,finish_reason=None,returned_model=None,error=type(exc).__name__,api_response=None)

def parse(raw,version,event):
    parsed=None;json_ok=False;format_ok=False;reason=''
    try:
        candidate=json.loads(raw);json_ok=isinstance(candidate,dict)
    except (ValueError,TypeError):candidate=None
    if version=='B':
        parsed=candidate if json_ok else None
        if not parsed:reason='not_json_object'
    else:
        matches=list(re.finditer(r'(?m)^(status|category|risk|evidence|missing_data|next_action):\s*',raw))
        if len(matches)==6 and [m.group(1) for m in matches]==list(FIELDS) and not raw[:matches[0].start()].strip():
            parsed={m.group(1):raw[m.end():matches[i+1].start() if i+1<len(matches) else len(raw)].strip() for i,m in enumerate(matches)}
        else:reason='six_headers_required'
    if isinstance(parsed,dict):
        ok=set(parsed)==set(FIELDS)
        ok=ok and parsed['status'] in ('assessed','insufficient_data') and parsed['category'] in ('normal','authentication_anomaly','phishing','malware','data_exposure','unknown') and parsed['risk'] in ('low','medium','high','critical','unknown')
        ok=ok and isinstance(parsed['next_action'],str) and bool(parsed['next_action'].strip())
        if version=='B':ok=ok and all(isinstance(parsed[k],list) and all(isinstance(x,str) for x in parsed[k]) for k in ('evidence','missing_data'))
        ok=ok and len(raw.split())<=180
        format_ok=bool(ok)
        if not format_ok:reason='schema_enum_or_word_limit'
    evidence=None
    if parsed:
        ev=parsed.get('evidence')
        if isinstance(ev,str):
            try:ev=json.loads(ev)
            except ValueError:ev=None
        if isinstance(ev,list) and all(isinstance(x,str) for x in ev):evidence=all(x in event for x in ev)
    category=parsed.get('category') if format_ok else None
    prediction='parse_error' if not format_ok else 'normal' if category=='normal' else 'abstain' if category=='unknown' else 'suspicious'
    return dict(parsed=parsed,json_ok=json_ok,format_ok=format_ok,format_error=reason,evidence_quotes_ok=evidence,predicted=prediction)

def percentile(values,q):
    xs=sorted(values);index=(len(xs)-1)*q;lo=math.floor(index);hi=math.ceil(index)
    return xs[lo]+(xs[hi]-xs[lo])*(index-lo)

def metrics(rows):
    n=len(rows);tp=sum(r['expected']=='suspicious' and r['predicted']=='suspicious' for r in rows);fp=sum(r['expected']=='normal' and r['predicted']=='suspicious' for r in rows)
    positives=sum(r['expected']=='suspicious' for r in rows)
    precision=tp/(tp+fp) if tp+fp else 0;recall=tp/positives if positives else 0
    matrix={truth:{pred:sum(r['expected']==truth and r['predicted']==pred for r in rows) for pred in ('normal','suspicious','abstain','parse_error')} for truth in ('normal','suspicious')}
    latency=[r['latency_s'] for r in rows]
    return dict(n=n,accuracy=sum(r['expected']==r['predicted'] for r in rows)/n,precision=precision,recall=recall,f1=2*precision*recall/(precision+recall) if precision+recall else 0,format_compliance=sum(r['format_ok'] for r in rows)/n,json_compliance=sum(r['json_ok'] for r in rows)/n,abstain=sum(r['predicted']=='abstain' for r in rows),parse_errors=sum(r['predicted']=='parse_error' for r in rows),tp=tp,fp=fp,missed_positive=positives-tp,mean_latency_s=statistics.mean(latency),median_latency_s=statistics.median(latency),p95_latency_s=percentile(latency,.95),input_tokens=sum(r['input_tokens'] or 0 for r in rows),output_tokens=sum(r['output_tokens'] or 0 for r in rows),usage_available=sum(r['input_tokens'] is not None and r['output_tokens'] is not None for r in rows),cost=None,confusion_matrix=matrix)

def summarize(run):
    records=[json.loads(s) for s in (run/'responses.jsonl').read_text(encoding='utf-8').splitlines()]
    save(run/'responses.json',records);csvsave(run/'responses.csv',[{k:v for k,v in r.items() if k!='api_response'} for r in records])
    main=[r for r in records if r['repeat']==0];report={v:metrics([r for r in main if r['version']==v]) for v in ('A','B') if any(r['version']==v for r in main)}
    save(run/'metrics.json',report);csvsave(run/'metrics.csv',[{'version':v,**m} for v,m in report.items()])
    cfg=read(run/'config/experiment.json');stability=[]
    for v in ('A','B'):
        for tid in cfg['repeat_ids']:
            rs=[r for r in records if r['version']==v and r['id']==tid]
            if not rs:continue
            labels=[r['predicted'] for r in rs]
            stability.append(dict(version=v,id=tid,n=len(rs),predictions=labels,distinct_labels=len(set(labels)),modal_share=max(collections.Counter(labels).values())/len(rs),format_compliance=sum(r['format_ok'] for r in rs)/len(rs),unique_raw_answers=len({r['raw'] for r in rs})))
    csvsave(run/'stability.csv',stability);save(run/'stability.json',stability)
    text='# Автоматическая сводка\n\n| Вариант | N | Accuracy | Precision | Recall | F1 | Формат | Средняя задержка с |\n|---|---|---|---|---|---|---|---|\n'
    for v,m in report.items():text+=f"| {v} | {m['n']} | {m['accuracy']:.3f} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | {m['format_compliance']:.3f} | {m['mean_latency_s']:.3f} |\n"
    (run/'summary.md').write_text(text+'\nМетрики относятся только к основным 30 примерам на вариант; повторы отдельно. Стоимость не оценивалась. Человеческая проверка не выполняется этим скриптом.\n',encoding='utf-8')

def judge(run):
    cfg=read(run/'config/experiment.json');tests={r['id']:r for r in read(run/'data/tests.json')}
    rows=[r for r in read(run/'responses.json') if r['repeat']==0 and r['id'] in cfg['review_ids']]
    path=run/'judge.jsonl';existing=[json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
    done={(r['version'],r['id']) for r in existing}
    for r in rows:
        if (r['version'],r['id']) in done:continue
        t=tests[r['id']]
        user=json.dumps(dict(policy=(run/'prompts'/cfg['versions'][r['version']]).read_text(encoding='utf-8'),event=t['input'],reference={'label':t['expected_label'],'category':t['expected_category'],'reason':t['reference_reason']},answer=r['raw']),ensure_ascii=False)
        out=call((run/'prompts/judge_v1.txt').read_text(encoding='utf-8'),user,cfg['judge_model'],cfg['judge_temperature'],cfg['judge_max_tokens'],cfg['timeout_s'])
        try:
            p=json.loads(out['raw']);valid=isinstance(p,dict) and set(p)==set(CRITERIA)|{'hallucination','explanations'} and all(type(p[k]) is int and 0<=p[k]<=2 for k in CRITERIA) and type(p['hallucination']) is bool and isinstance(p['explanations'],dict) and set(p['explanations'])==set(CRITERIA) and all(isinstance(x,str) and x.strip() for x in p['explanations'].values())
        except (ValueError,TypeError,KeyError):p=None;valid=False
        item={'version':r['version'],'id':r['id'],**out,'parsed':p,'judge_format_ok':bool(valid)}
        with path.open('a',encoding='utf-8') as f:f.write(json.dumps(item,ensure_ascii=False)+'\n')
        existing.append(item);print('judge',r['version'],r['id'],valid,out['error'],round(out['latency_s'],2),flush=True)
    save(run/'judge.json',existing);csvsave(run/'judge.csv',[{k:v for k,v in r.items() if k!='api_response'} for r in existing])

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path);p.add_argument('--judge-only',action='store_true');p.add_argument('--with-judge',action='store_true');p.add_argument('--summarize-only',action='store_true');a=p.parse_args()
    run=a.run
    if not run:
        run=ROOT/'results'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S_utc');run.mkdir(parents=True)
        for folder in ('data','prompts','config','src'):shutil.copytree(ROOT/folder,run/folder)
        metadata={'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'python':platform.python_version(),'system':platform.system(),'seed':None,'order':'per-example A then B, then repeats 1..3 A then B','retries':0,'input_sha256':hashlib.sha256((run/'data/tests.json').read_bytes()).hexdigest(),'cost':'not estimated; local compute and electricity not priced'}
        try:
            base,_=env();metadata['models']=json.load(urllib.request.urlopen(base.removesuffix('/v1')+'/api/v0/models',timeout=10))
        except Exception:metadata['models']=None
        save(run/'metadata.json',metadata)
    print('RUN',run,flush=True)
    if a.judge_only:judge(run);return
    if a.summarize_only:summarize(run);return
    cfg=read(run/'config/experiment.json');tests=read(run/'data/tests.json');path=run/'responses.jsonl'
    done={(r['version'],r['id'],r['repeat']) for r in [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]} if path.exists() else set()
    for repeat in range(cfg['additional_repeats']+1):
        for t in tests:
            if repeat and t['id'] not in cfg['repeat_ids']:continue
            for v,filename in cfg['versions'].items():
                if (v,t['id'],repeat) in done:continue
                # Identical user template for both historical prompts. No label/reference leakage.
                user='Учебное событие для анализа:\n'+t['input']
                out=call((run/'prompts'/filename).read_text(encoding='utf-8'),user,cfg['model'],cfg['temperature'],cfg['max_tokens'],cfg['timeout_s'])
                item={'version':v,'prompt_version':filename,'id':t['id'],'difficulty':t['difficulty'],'repeat':repeat,'expected':t['expected_label'],'expected_category':t['expected_category'],'input':t['input'],**out,**parse(out['raw'],v,t['input'])}
                with path.open('a',encoding='utf-8') as f:f.write(json.dumps(item,ensure_ascii=False)+'\n')
                print(v,t['id'],repeat,item['predicted'],out['error'],round(out['latency_s'],2),flush=True)
    summarize(run)
    if a.with_judge:judge(run)

if __name__=='__main__':main()
