from common import *
def chunks(corpus,size,overlap,label):
 result=[]
 for source in sorted({d['source'] for d in corpus}):
  text=(ROOT/'data/documents'/source).read_text(encoding='utf-8')
  start=0;n=0
  while start<len(text):
   end=min(start+size,len(text));n+=1
   # All intersecting base IDs are provenance, not the retrieval gold labels.
   parents=[d['id'] for d in corpus if d['source']==source and d['end']>start and d['start']<end]
   result.append(dict(id=f'{label}_{source[:-4]}_{n:02}',text=text[start:end],source=source,start=start,end=end,base_ids=parents,access_group='admins' if source=='network.txt' else 'students'))
   if end==len(text):break
   start=end-overlap
 return result
def build(model):
 out=ROOT/'results';out.mkdir(exist_ok=True);corpus=readlines(ROOT/'data/corpus.jsonl');cfg=readjson(ROOT/'config.json')
 schemes={'base':corpus}
 for s in cfg['chunk_schemes']:schemes[s['name']]=chunks(corpus,s['size'],s['overlap'],s['name'])
 stats=[]
 for name,docs in schemes.items():
  t=time.perf_counter();emb=encode(model,[d['text'] for d in docs]);elapsed=time.perf_counter()-t
  assert emb.shape==(len(docs),cfg['dimension']);assert np.allclose(np.linalg.norm(emb,axis=1),1,atol=1e-5)
  np.save(out/f'{name}_embeddings.npy',emb);save(out/f'{name}_documents.json',docs)
  stats.append(dict(scheme=name,fragments=len(docs),dimension=emb.shape[1],encoding_and_matrix_s=elapsed,vector_bytes=emb.nbytes,max_tokens=max(len(model.tokenizer(d['text'])['input_ids']) for d in docs)))
 save(out/'index_stats.json',stats);return schemes
if __name__=='__main__':build(load_model())
