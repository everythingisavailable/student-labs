import argparse,csv,hashlib,platform,time,sys
from pathlib import Path
from rag_search import *
from local_api import LocalAPI

def writecsv(p,rows):
    if not rows:return
    with Path(p).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--generate',action='store_true');ap.add_argument('--search',action='store_true');args=ap.parse_args()
    cfg=readjson(ROOT/'configs/experiments.json');questions=jsonl(ROOT/'data/questions.jsonl');model=load_model()
    indexes={};searchrows=[];summary=[]
    if args.search:
        for c in cfg['configs']:
            key=(c['chunk_size'],c['overlap'])
            if key not in indexes:indexes[key]=Index(model,*key)
            idx=indexes[key];rows=[]
            for repeat in range(cfg['retrieval_repeats']):
                for q in questions:
                    res=idx.retrieve(q['question'],c['top_k'],c['mode'],c['candidate_n'],c['context_budget_chars'])
                    row={'experiment_id':c['id'],'repeat':repeat,'question_id':q['id'],'answerable':q['answerable'],**res,**metrics(res['chunks'],q['gold_doc_ids'])}
                    row['candidate_hit']=int(bool(set(res['candidate_doc_ids'])&set(q['gold_doc_ids']))) if q['answerable'] else None
                    rows.append(row)
            searchrows.extend(rows);valid=[r for r in rows if r['answerable']]
            s={**c,'n_chunks':len(idx.chunks),'build_s':idx.build_s}
            for metric in ['hit','recall','mrr','candidate_hit','context_chars','retrieval_s','rerank_s']:s[metric]=float(np.mean([r[metric] for r in valid]))
            s['unique_docs']=float(np.mean([len(set(c['doc_id'] for c in r['chunks'])) for r in valid]))
            summary.append(s);print(c['id'],s['hit'],s['recall'],s['mrr'],flush=True)
        (ROOT/'results/search_runs.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in searchrows),encoding='utf-8')
        writecsv(ROOT/'results/summary.csv',summary);save(ROOT/'results/summary.json',summary)
        save(ROOT/'results/environment.json',{'python':platform.python_version(),'platform':platform.platform(),'model':cfg['embedding_model'],'revision':cfg['revision'],'max_seq_length':cfg['max_seq_length'],'corpus_sha256':hashlib.sha256((ROOT/'data/corpus.jsonl').read_bytes()).hexdigest(),'questions_sha256':hashlib.sha256((ROOT/'data/questions.jsonl').read_bytes()).hexdigest()})
    if args.generate:
        system=(ROOT/'configs/system.txt').read_text(encoding='utf-8')
        out=ROOT/'results/generation.jsonl';done=set()
        if out.exists():done={(r['experiment_id'],r['question_id'],r['seed']) for r in jsonl(out)}
        # Interleave configurations per question/repeat to reduce time-order confounding.
        for seed in cfg['seeds']:
            for q in questions:
                for c in cfg['configs']:
                    if c['id'] not in cfg['generation_config_ids'] or (c['id'],q['id'],seed) in done:continue
                    key=(c['chunk_size'],c['overlap'])
                    if key not in indexes:indexes[key]=Index(model,*key)
                    found=indexes[key].retrieve(q['question'],c['top_k'],c['mode'],c['candidate_n'],c['context_budget_chars'])
                    text=context(found['chunks']);messages=[{'role':'system','content':system},{'role':'user','content':f"CONTEXT\n{text}\nEND CONTEXT\nВопрос: {q['question']}"}]
                    api=LocalAPI(cfg['llm_model'],cfg['temperature'],cfg['max_tokens'],seed)
                    t=time.perf_counter()
                    try:answer=api.chat(messages,timeout=180);error=None
                    except Exception as e:answer={};error=type(e).__name__
                    row={'experiment_id':c['id'],'question_id':q['id'],'seed':seed,'question':q['question'],'answerable':q['answerable'],'found':found,'context':text,'prompt_chars':sum(len(m['content']) for m in messages),'answer':answer.get('content',''),'error':error,'llm_s':time.perf_counter()-t,'api_records':api.records}
                    with out.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
                    print(c['id'],q['id'],seed,'error='+str(error),flush=True)
                    if error:raise RuntimeError('Inference failed; inspect saved record before resuming')
if __name__=='__main__':main()
