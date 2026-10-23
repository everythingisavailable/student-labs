import argparse
from common import *
def search(query,model,k=3,role='students',scheme='base'):
 if k<1:raise ValueError('k must be positive')
 docs=readjson(ROOT/f'results/{scheme}_documents.json');emb=np.load(ROOT/f'results/{scheme}_embeddings.npy',allow_pickle=False)
 scores=emb@encode(model,[query])[0];order=ranked(scores,docs,role)[:k]
 return [dict(**docs[int(i)],score=float(scores[i])) for i in order]
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('query');ap.add_argument('--k',type=int,default=3);ap.add_argument('--role',choices=['students','admins'],default='students');a=ap.parse_args()
 print(json.dumps(search(a.query,load_model(),a.k,a.role),ensure_ascii=False,indent=2))
