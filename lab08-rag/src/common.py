"""Local embedding retrieval. No cloud inference or trusted remote model code."""
from pathlib import Path
import json,os,time
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY','1')
os.environ.setdefault('HF_HUB_DISABLE_IMPLICIT_TOKEN','1')
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def readjson(p):return json.loads(p.read_text(encoding='utf-8'))
def readlines(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]
def save(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def load_model():
 import torch
 from sentence_transformers import SentenceTransformer
 cfg=readjson(ROOT/'config.json');torch.set_num_threads(cfg['threads']);torch.manual_seed(cfg['seed']);np.random.seed(cfg['seed'])
 model=SentenceTransformer(os.getenv('LAB7_MODEL_PATH',cfg['model']),revision=cfg['revision'],device='cpu',trust_remote_code=False)
 model.max_seq_length=cfg['max_seq_length']
 return model
def encode(model,texts):
 lengths=[len(model.tokenizer(t,truncation=False)['input_ids']) for t in texts]
 if max(lengths,default=0)>model.max_seq_length:raise ValueError('Input exceeds fixed token limit; do not silently truncate')
 return model.encode(texts,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False).astype('float32')
def allowed_indices(docs,role):
 if role not in ['students','admins']:raise ValueError('Unknown role')
 return np.array([i for i,d in enumerate(docs) if d['access_group']=='students' or role=='admins'],dtype=int)
def ranked(scores,docs,role='admins'):
 # Filter before ranking and before exposing text, metadata or scores.
 allowed=allowed_indices(docs,role)
 return allowed[np.argsort(-scores[allowed],kind='stable')]
def metrics(order,docs,relevant,k):
 relevant=set(relevant);ids=[docs[int(i)]['id'] for i in order]
 rank=next((i for i,d in enumerate(ids,1) if d in relevant),None)
 hits=len(set(ids[:k])&relevant)
 return dict(precision=hits/k,recall=hits/len(relevant) if relevant else 0,mrr=1/rank if rank else 0,first_relevant_rank=rank)
