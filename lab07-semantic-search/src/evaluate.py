import csv,hashlib,platform,statistics,importlib.metadata as md
from datetime import datetime,timezone
import psutil
from sklearn.feature_extraction.text import TfidfVectorizer
from common import *
from build_index import build

def gold_for_chunks(query,docs,base):
 # >=50% of a relevant base paragraph must be present in a chunk.
 # Full definition fixed in code before the first retrieval run.
 gold=[]
 for d in docs:
  for b in base:
   if b['id'] in query['relevant_ids'] and b['source']==d['source']:
    overlap=max(0,min(b['end'],d['end'])-max(b['start'],d['start']))
    if overlap/(b['end']-b['start'])>=.5:gold.append(d['id']);break
 return gold
def main():
 cfg=readjson(ROOT/'config.json');queries=readlines(ROOT/'data/queries.jsonl');manifest=readjson(ROOT/'data/pre_experiment_manifest.json')
 for name,sha in manifest['sha256'].items():assert hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest()==sha
 started=datetime.now(timezone.utc).isoformat();t=time.perf_counter();model=load_model();load_s=time.perf_counter()-t
 encode(model,['Прогрев модели перед измерениями.']);schemes=build(model);base=schemes['base'];out=ROOT/'results'
 rows=[]
 for scheme,docs in schemes.items():
  embeddings=np.load(out/f'{scheme}_embeddings.npy',allow_pickle=False)
  tf=TfidfVectorizer(lowercase=True,ngram_range=(1,2),sublinear_tf=True);t=time.perf_counter();matrix=tf.fit_transform([d['text'] for d in docs]);tfbuild=time.perf_counter()-t
  print('EVALUATE',scheme,len(docs),flush=True)
  for q in queries:
   gold=q['relevant_ids'] if scheme=='base' else gold_for_chunks(q,docs,base)
   assert gold,(scheme,q['id'])
   for method in ['tfidf','semantic']:
    for rep in range(1,cfg['repeats']+1):
     t=time.perf_counter()
     if method=='semantic':vec=encode(model,[q['text']])[0];encoded=time.perf_counter();scores=embeddings@vec
     else:vec=tf.transform([q['text']]);encoded=time.perf_counter();scores=(matrix@vec.T).toarray().ravel()
     order=ranked(scores,docs);end=time.perf_counter()
     rows.append(dict(scheme=scheme,method=method,query_id=q['id'],query=q['text'],repeat=rep,gold_ids=gold,latency_ms=(end-t)*1000,encode_ms=(encoded-t)*1000,rank_ms=(end-encoded)*1000,ranking=[dict(id=docs[int(i)]['id'],score=float(scores[i])) for i in order],metrics={str(k):metrics(order,docs,gold,k) for k in cfg['top_k']}))
  save(out/f'{scheme}_tfidf_build.json',dict(seconds=tfbuild,features=len(tf.vocabulary_)))
 save(out/'runs.json',rows)
 summaries=[]
 for scheme in schemes:
  for method in ['tfidf','semantic']:
   rr=[r for r in rows if r['scheme']==scheme and r['method']==method]
   for k in cfg['top_k']:
    summaries.append(dict(scheme=scheme,method=method,k=k,n_queries=len(queries),repeats=cfg['repeats'],precision=statistics.mean(r['metrics'][str(k)]['precision'] for r in rr),recall=statistics.mean(r['metrics'][str(k)]['recall'] for r in rr),mrr=statistics.mean(r['metrics'][str(k)]['mrr'] for r in rr),latency_ms=statistics.mean(r['latency_ms'] for r in rr),latency_stdev_ms=statistics.stdev(r['latency_ms'] for r in rr),encode_ms=statistics.mean(r['encode_ms'] for r in rr),rank_ms=statistics.mean(r['rank_ms'] for r in rr)))
 save(out/'metrics.json',summaries)
 with (out/'summary.csv').open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(summaries[0]));w.writeheader();w.writerows(summaries)
 with (out/'search_results.csv').open('w',encoding='utf-8-sig',newline='') as f:
  fields=['scheme','method','query_id','repeat','top1','top3','first_relevant_rank','precision_at3','recall_at3','latency_ms'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for r in rows:w.writerow(dict(scheme=r['scheme'],method=r['method'],query_id=r['query_id'],repeat=r['repeat'],top1=r['ranking'][0]['id'],top3=';'.join(x['id'] for x in r['ranking'][:3]),first_relevant_rank=r['metrics']['3']['first_relevant_rank'],precision_at3=r['metrics']['3']['precision'],recall_at3=r['metrics']['3']['recall'],latency_ms=r['latency_ms']))
 # Real retrieval ACL checks on every test query, both groups; no hidden text/scores returned.
 from search import search
 acl=[]
 for q in queries:
  result=search(q['text'],model,k=40,role='students');assert all(d['access_group']=='students' for d in result);assert len(result)==32
  acl.append(dict(query_id=q['id'],returned=len(result),restricted_returned=0))
 save(out/'acl_checks.json',acl)
 save(out/'environment.json',dict(started_utc=started,finished_utc=datetime.now(timezone.utc).isoformat(),python=platform.python_version(),os=platform.system()+' '+platform.release(),cpu_description=platform.processor(),logical_processors=psutil.cpu_count(),physical_cores=psutil.cpu_count(logical=False),ram_gib=psutil.virtual_memory().total/2**30,threads=cfg['threads'],device='cpu',model_load_s=load_s,packages={n:md.version(n) for n in ['sentence-transformers','torch','transformers','numpy','scikit-learn','psutil','huggingface-hub']},model=cfg['model'],revision=cfg['revision'],max_seq_length=model.max_seq_length,telemetry_disabled=True,cloud_inference=False))
 print(json.dumps([s for s in summaries if s['k']==3],indent=2),flush=True)
if __name__=='__main__':main()
