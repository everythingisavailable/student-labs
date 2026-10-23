from common import *

class Retriever:
    def __init__(self):
        self.model=load_model()
        self.documents=readjson(ROOT/'data/index_documents.json')
        self.vectors=np.load(ROOT/'data/embeddings.npy',allow_pickle=False)
        if self.vectors.shape != (len(self.documents),384):raise ValueError('Invalid matrix shape')
    def retrieve(self,query,k=4,role='students'):
        if k not in range(1,41):raise ValueError('k must be between 1 and 40')
        # Validate role before encoding/ranking, then only expose authorized records.
        allowed_indices(self.documents,role)
        scores=self.vectors@encode(self.model,[query])[0]
        order=ranked(scores,self.documents,role)
        results=[dict(**self.documents[int(i)],score=float(scores[i])) for i in order[:k]]
        for d in results:
            if role!='admins' and d['access_group']!='students':raise PermissionError('Access changed')
        return results,[self.documents[int(i)]['id'] for i in order]
