import argparse,json,sys,time
from pathlib import Path
from soc_tools import Dispatcher,TOOLS,SYSTEM,ROOT,valid_calls
from local_api import LocalAPI

def single_turn(query,api,dispatcher,use_tools=True,max_calls=3,max_seconds=240):
    start=time.monotonic();messages=[{'role':'system','content':SYSTEM},{'role':'user','content':query}];trace=[];status='completed';answer=''
    def remaining():return min(90,max_seconds-(time.monotonic()-start))
    try:
        msg=api.chat(messages,TOOLS if use_tools else None,timeout=remaining());messages.append(msg)
        calls=msg.get('tool_calls') or []
        if not valid_calls(calls):return {'status':'protocol_error','answer':'','trace':trace,'messages':messages,'latency_s':time.monotonic()-start}
        ids=[c.get('id') for c in calls]
        if len(set(ids))!=len(ids) or any(not isinstance(i,str) or not i for i in ids):raise ValueError('invalid_call_ids')
        if calls and not use_tools:status='unexpected_tool_calls'
        elif calls:
            for i,c in enumerate(calls):
                name=c.get('function',{}).get('name');raw=c.get('function',{}).get('arguments');t=time.monotonic()
                if remaining()<=0:result={'error':'time_limit'};status='time_limit'
                elif i>=max_calls:result={'error':'tool_budget_exceeded'};status='tool_budget_exceeded'
                else:result=dispatcher.dispatch(name,raw)
                trace.append({'name':name,'arguments':raw,'result':result,'latency_s':time.monotonic()-t})
                messages.append({'role':'tool','tool_call_id':c['id'],'content':json.dumps(result,ensure_ascii=False)})
            if status=='completed':
                if remaining()<=0:status='time_limit'
                else:
                    msg=api.chat(messages,tools=None,timeout=remaining());messages.append(msg)
                    if msg.get('tool_calls'):status='unexpected_tool_calls'
        answer=msg.get('content') or ''
        if status=='completed' and not answer.strip():status='empty_answer'
        if remaining()<=0:status='time_limit'
    except TimeoutError:status='time_limit'
    except Exception:status='api_error'
    return {'status':status,'answer':answer,'trace':trace,'messages':messages,'latency_s':time.monotonic()-start}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--benchmark',action='store_true');ap.add_argument('--query',default='Покажи сведения об инциденте INC-101.');args=ap.parse_args()
    from rag_search import Index,load_model,readjson,jsonl
    index=Index(load_model(),600,100);dispatch=Dispatcher(index)
    cfg=readjson(ROOT/'configs/protocol.json');cases=readjson(ROOT/'configs/cases.json');out=ROOT/'results/runs.jsonl'
    if not args.benchmark:print(json.dumps(single_turn(args.query,LocalAPI(model=cfg['model'],max_tokens=700),dispatch),ensure_ascii=False,indent=2));return
    done={(r['case_id'],r['seed'],r['mode']) for r in jsonl(out)} if out.exists() else set()
    for seed in cfg['seeds']:
        for case in cases:
            for mode in cfg['modes']:
                if (case['id'],seed,mode) in done:continue
                api=LocalAPI(cfg['model'],cfg['temperature'],cfg['max_tokens'],seed)
                row=single_turn(case['query'],api,dispatch,mode=='with_tools',cfg['max_calls'],cfg['max_seconds'])
                row.update(case_id=case['id'],seed=seed,mode=mode,query=case['query'],api_records=api.records)
                with out.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
                print(mode,case['id'],seed,row['status'],flush=True)
                if row['status']=='api_error':raise RuntimeError('Inspect API error before resume')
if __name__=='__main__':main()
