"""Rebuild Lab7-compatible embeddings from the preserved corpus, if needed."""
import hashlib
from common import *
if __name__=='__main__':
    corpus=readlines(ROOT/'data/corpus.jsonl');model=load_model()
    vectors=encode(model,[d['text'] for d in corpus]);np.save(ROOT/'data/embeddings.npy',vectors)
    save(ROOT/'data/index_documents.json',corpus)
    # Rebuilding changes byte hashes; keep the original provenance for reference.
    save(ROOT/'data/rebuild_manifest.json',dict(model=readjson(ROOT/'config.json')['model'],sha256=hashlib.sha256((ROOT/'data/embeddings.npy').read_bytes()).hexdigest()))
    print(vectors.shape)
