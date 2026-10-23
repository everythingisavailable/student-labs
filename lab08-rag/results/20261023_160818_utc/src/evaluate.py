import hashlib,platform,importlib.metadata as md,random
from datetime import datetime,timezone
import psutil
from common import *
from rag import rag_answer
from retrieve import Retriever
from llm import api_request
from prompt import SYSTEM_PROMPT

def main():
    cfg=readjson(ROOT/'config.json');questions=readlines(ROOT/'data/questions.jsonl')
    run=ROOT/'results'/datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_utc');run.mkdir()
    import shutil
    for name in ['src','data']:shutil.copytree(ROOT/name,run/name,ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(ROOT/'config.json',run/'config.json')
    models=api_request('/api/v1/models');selected=next(m for m in models['models'] if m['key']==cfg['llm_model'])
    if not selected.get('loaded_instances'):raise RuntimeError('Selected model is not loaded')
    save(run/'llm_model.json',selected)
    t=time.perf_counter();retriever=Retriever();load_s=time.perf_counter()-t
    encode(retriever.model,['Прогрев поиска.'])
    jobs=[(q,k) for q in questions for k in cfg['top_k']];random.Random(42).shuffle(jobs)
    save(run/'plan.json',[dict(question_id=q['id'],k=k) for q,k in jobs])
    save(run/'environment.json',dict(utc=datetime.now(timezone.utc).isoformat(),python=platform.python_version(),os=platform.system()+' '+platform.release(),cpu=platform.processor(),logical_processors=psutil.cpu_count(),physical_cores=psutil.cpu_count(logical=False),ram_gib=psutil.virtual_memory().total/2**30,embedding_load_s=load_s,offline_embeddings=os.getenv('HF_HUB_OFFLINE')=='1',packages={n:md.version(n) for n in ['numpy','torch','sentence-transformers','transformers']},seed_sent=cfg['llm_seed'],seed_reproducibility_verified=False))
    print('RUN',run,flush=True)
    for i,(q,k) in enumerate(jobs,1):
        r=rag_answer(q['question'],retriever,k,cfg['experiment_role']);r.update(question_id=q['id'],kind=q['kind'],gold_ids=q['gold_ids'],expected=q['expected'],sequence=i)
        gold=set(q['gold_ids']);top={d['id'] for d in r['retrieved']};rank=next((i for i,id in enumerate(r['ranking'],1) if id in gold),None)
        r['retrieval_metrics']=dict(recall=len(gold&top)/len(gold) if gold else None,mrr=1/rank if rank else None,mrr_at_k=1/rank if rank and rank<=k else 0 if gold else None,all_gold_found=gold<=top if gold else None)
        with (run/'runs.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(r,ensure_ascii=False)+'\n')
        print(i,q['id'],k,round(r['total_s'],2),r['error'],flush=True)
    # Access checks reuse all test queries and compare transmitted context eligibility.
    acl=[]
    for q in questions:
        results,_=retriever.retrieve(q['question'],40,'students');assert len(results)==32 and all(d['access_group']=='students' for d in results)
        acl.append(dict(question_id=q['id'],restricted_returned=0,allowed_count=len(results)))
    save(run/'acl_checks.json',acl)
    (ROOT/'results/latest.txt').write_text(run.name+'\n',encoding='utf-8')
if __name__=='__main__':main()
