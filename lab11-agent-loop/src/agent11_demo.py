"""Bounded agent state machine: simulated controller tests and real API runs."""
from pathlib import Path
import argparse,json,sys,time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'lab10-tool-calling/src'))
from soc_tools import Dispatcher,TOOLS,SYSTEM,validated,valid_calls
from local_api import LocalAPI

AGENT_SYSTEM = SYSTEM + '''\nРаботай последовательно: ровно один вызов инструмента за ход.
Сначала получи карточку. На следующем ходе используй только конкретный IP из полученного ответа.
Нельзя передавать шаблоны, переменные, выражения {{...}} или ссылки на будущий результат в аргументах.
После каждого результата выбери следующий нужный инструмент. Для регламента ищи по уровню high или low из карточки.
Когда все необходимые сведения получены, дай обычный текст: ID, факты, условный риск IP, рекомендация и doc_id/chunk_id.
Финальный ответ не должен быть списком планируемых вызовов или JSON-шаблоном.
Если записи нет, сразу сообщи об отсутствии. Не придумывай причину отсутствия.'''

def call(name,arguments,cid):return {'id':cid,'type':'function','function':{'name':name,'arguments':json.dumps(arguments,ensure_ascii=False)}}
class ScriptedAPI:
    def __init__(self,script):self.script=iter(script);self.records=[]
    def chat(self,messages,tools=None,timeout=90):
        msg=next(self.script);self.records.append({'request_messages':json.loads(json.dumps(messages)),'response':msg});return msg
def demo_api():return ScriptedAPI([
    {'role':'assistant','tool_calls':[call('get_incident',{'incident_id':'INC-101'},'d1')]},
    {'role':'assistant','tool_calls':[call('lookup_ip',{'ip':'203.0.113.42'},'d2')]},
    {'role':'assistant','tool_calls':[call('search_knowledge_base',{'query':'high-инцидент эскалация KB-01'},'d3')]},
    {'role':'assistant','content':'INC-101: учебный уровень high, условный риск IP high. По KB-01 рекомендуется эскалация дежурному руководителю SOC. Подтверждённой компрометации в карточке нет. Ничего не изменено. [soc]'}])

def run_agent(query,api,dispatcher,max_rounds=6,max_calls=8,max_seconds=240,clock=time.monotonic):
    if min(max_rounds,max_calls,max_seconds)<=0:raise ValueError('invalid_budget')
    start=clock();messages=[{'role':'system','content':AGENT_SYSTEM},{'role':'user','content':query}]
    trace=[];seen=set();used=0;rounds=0;answer='';status='round_limit';issued_ids=set()
    def remaining():return max_seconds-(clock()-start)
    for round_no in range(1,max_rounds+1):
        if remaining()<=0:status='time_limit';break
        rounds=round_no
        try:msg=api.chat(messages,TOOLS,timeout=min(90,remaining()))
        except TimeoutError:status='time_limit';break
        except Exception:status='api_error';break
        if remaining()<=0:status='time_limit';break
        calls=msg.get('tool_calls') or []
        if not valid_calls(calls):status='protocol_error';break
        if not calls:
            answer=msg.get('content') or '';messages.append(msg);status='completed' if answer.strip() else 'empty_answer';break
        ids=[c.get('id') for c in calls]
        if len(calls)>20 or any(not isinstance(i,str) or not i or i in issued_ids for i in ids) or len(set(ids))!=len(ids):status='protocol_error';break
        issued_ids.update(ids);messages.append(msg)
        budget_failed=False;timed_out=False
        for c in calls:
            name=c.get('function',{}).get('name');raw=c.get('function',{}).get('arguments');args,error=validated(name,raw);t=clock()
            if remaining()<=0:result={'error':'time_limit'};timed_out=True
            elif used>=max_calls:result={'error':'tool_budget_exceeded'};budget_failed=True
            else:
                # Attempts (including invalid/repeated) consume budget, preventing unbounded abuse.
                used+=1
                key=(name,json.dumps(args,sort_keys=True,ensure_ascii=False)) if args is not None else None
                if error:result={'error':error}
                elif key in seen:result={'error':'repeated_call'}
                else:
                    seen.add(key);result=dispatcher.dispatch(name,raw)
            trace.append({'round':round_no,'call_id':c['id'],'name':name,'arguments':raw,'result':result,'latency_s':clock()-t})
            messages.append({'role':'tool','tool_call_id':c['id'],'content':json.dumps(result,ensure_ascii=False)})
        if timed_out or remaining()<=0:status='time_limit';break
        if budget_failed:status='tool_budget_exceeded';break
    return {'status':status,'rounds':rounds,'calls':used,'answer':answer,'trace':trace,'messages':messages,'latency_s':clock()-start}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--demo',action='store_true');ap.add_argument('--benchmark',action='store_true');ap.add_argument('--self-test',action='store_true');args=ap.parse_args()
    if args.self_test:
        import unittest
        suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'));r=unittest.TextTestRunner(verbosity=2).run(suite);sys.exit(0 if r.wasSuccessful() else 1)
    if args.demo:
        class DemoSearch:
            def retrieve(self,*args,**kwargs):return {'chunks':[{'doc_id':'soc','chunk_id':'demo:KB-01','text':'KB-01. При high-инциденте аналитик передаёт сведения дежурному руководителю SOC для эскалации.','access_group':'admins'}]}
        row=run_agent('Разбери INC-101',demo_api(),Dispatcher(DemoSearch()));row['mode']='scripted_demo';print(json.dumps(row,ensure_ascii=False,indent=2));return
    from rag_search import Index,load_model,readjson,jsonl
    idx=Index(load_model(),600,100);dispatcher=Dispatcher(idx);cfg=readjson(ROOT/'configs/protocol.json');cases=readjson(ROOT/'configs/cases.json')
    if not args.benchmark:
        print(json.dumps(run_agent(cases[0]['query'],LocalAPI(model=cfg['model'],max_tokens=700),dispatcher),ensure_ascii=False,indent=2));return
    out=ROOT/'results/runs.jsonl';done={(r['case_id'],r['seed'],r['max_rounds']) for r in jsonl(out)} if out.exists() else set()
    save_demo=run_agent(cases[0]['query'],demo_api(),dispatcher);save_demo['mode']='scripted_demo'
    (ROOT/'results/demo_trace.json').write_text(json.dumps(save_demo,ensure_ascii=False,indent=2),encoding='utf-8')
    for seed in cfg['seeds']:
        for case in cases:
            for rounds in cfg['max_rounds']:
                if (case['id'],seed,rounds) in done:continue
                api=LocalAPI(cfg['model'],cfg['temperature'],cfg['max_tokens'],seed)
                row=run_agent(case['query'],api,dispatcher,rounds,cfg['max_calls'],cfg['max_seconds'])
                row.update(case_id=case['id'],seed=seed,max_rounds=rounds,mode='real',query=case['query'],api_records=api.records)
                with out.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
                print(case['id'],seed,rounds,row['status'],row['calls'],flush=True)
                if row['status']=='api_error':raise RuntimeError('Inspect saved API error')
if __name__=='__main__':main()
