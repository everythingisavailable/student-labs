"""Versioned retrieval, document metrics and bounded contexts for Labs9–11."""
from pathlib import Path
import os,json,time,re
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY','1')
os.environ.setdefault('HF_HUB_DISABLE_IMPLICIT_TOKEN','1')
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
ROOT=Path(__file__).resolve().parents[1]
def readjson(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def jsonl(p):return [json.loads(s) for s in Path(p).read_text(encoding='utf-8').splitlines() if s.strip()]
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def chunks_for(doc,size,overlap):
    if not 0<=overlap<size:raise ValueError('invalid_chunk_config')
    text=' '.join(doc['text'].split());pos=0;chunks=[]
    while pos<len(text):
        end=min(pos+size,len(text))
        if end<len(text):
            cut=text.rfind(' ',pos+size//2,end)
            if cut>pos:end=cut
        chunks.append({'doc_id':doc['doc_id'],'chunk_id':f"{doc['doc_id']}:{size}:{overlap}:{len(chunks)}",'text':text[pos:end],'start':pos,'end':end,'access_group':doc['access_group']})
        if end==len(text):break
        pos=max(pos+1,end-overlap)
        # Never begin in the middle of a word; actual overlap is logged by offsets.
        while pos<end and pos>0 and text[pos-1]!=' ':pos+=1
    return chunks
def load_model():
    import torch
    from sentence_transformers import SentenceTransformer
    cfg=readjson(ROOT/'configs/experiments.json')
    torch.set_num_threads(cfg['threads']);torch.manual_seed(7);np.random.seed(7)
    local=os.getenv('EMBEDDING_MODEL_PATH')
    model=SentenceTransformer(local or cfg['embedding_model'],revision=cfg['revision'],device='cpu',trust_remote_code=False,local_files_only=bool(local))
    model.max_seq_length=cfg['max_seq_length']
    return model
def encode(model,texts):
    sizes=[len(model.tokenizer(t,truncation=False)['input_ids']) for t in texts]
    if max(sizes,default=0)>model.max_seq_length:raise ValueError('embedding_truncation_forbidden')
    return model.encode(texts,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False).astype('float32')
class Index:
    def __init__(self,model,size=600,overlap=100,role='admins',docs=None):
        if role not in ('students','admins'):raise ValueError('invalid_role')
        self.model=model;self.role=role;t=time.perf_counter()
        docs=docs if docs is not None else jsonl(ROOT/'data/corpus.jsonl')
        # ACL before embedding/index construction; disallowed source text never enters this index.
        self.chunks=[c for d in docs if d['access_group']=='students' or role=='admins' for c in chunks_for(d,size,overlap)]
        self.dense=encode(model,[c['text'] for c in self.chunks])
        self.tfidf=TfidfVectorizer(analyzer='char',ngram_range=(3,5))
        self.lexical=self.tfidf.fit_transform(c['text'] for c in self.chunks)
        self.build_s=time.perf_counter()-t
    def retrieve(self,query,k=4,mode='dense',candidate_n=12,budget=10000):
        if not isinstance(query,str) or not 1<=len(query.strip())<=500:raise ValueError('invalid_query')
        if mode not in ('dense','hybrid','lexical','rerank'):raise ValueError('invalid_mode')
        if not 1<=k<=12 or not 1<=candidate_n<=50:raise ValueError('invalid_count')
        t=time.perf_counter();q=encode(self.model,[query])[0]
        ds=self.dense@q;ls=(self.lexical@self.tfidf.transform([query]).T).toarray().ravel()
        d=np.argsort(-ds,kind='stable');l=np.argsort(-ls,kind='stable')
        cand=d[:candidate_n].tolist();rerank_s=0
        if mode=='hybrid':
            dr=np.empty(len(d));lr=np.empty(len(d));dr[d]=np.arange(1,len(d)+1);lr[l]=np.arange(1,len(d)+1)
            scores=1/(60+dr)+1/(60+lr);order=np.argsort(-scores,kind='stable')
        elif mode=='lexical':order=l;scores=ls
        elif mode=='rerank':
            tr=time.perf_counter();scores=.65*ds+.35*ls
            order=np.array(cand)[np.argsort(-scores[cand],kind='stable')];rerank_s=time.perf_counter()-tr
        else:order=d;scores=ds
        selected=[];used=0
        for idx in order[:k]:
            c=dict(self.chunks[int(idx)]);c['score']=float(scores[idx])
            # Whole chunks only: no hidden truncation of a cited fact.
            if used+len(c['text'])>budget:continue
            selected.append(c);used+=len(c['text'])
        return {'chunks':selected,'context_chars':used,'retrieval_s':time.perf_counter()-t,'rerank_s':rerank_s,'candidate_chunks':[self.chunks[i]['chunk_id'] for i in cand],'candidate_doc_ids':list(dict.fromkeys(self.chunks[i]['doc_id'] for i in cand))}
def metrics(found,gold):
    ids=list(dict.fromkeys(c['doc_id'] for c in found));gold=set(gold)
    if not gold:return {'hit':None,'recall':None,'mrr':None}
    rank=next((i for i,x in enumerate(ids,1) if x in gold),None)
    return {'hit':int(bool(gold.intersection(ids))),'recall':len(gold.intersection(ids))/len(gold),'mrr':1/rank if rank else 0}
def context(chunks):
    return '\n\n'.join(f"[S{i}] doc_id={c['doc_id']} chunk_id={c['chunk_id']}\n{c['text']}" for i,c in enumerate(chunks,1))
