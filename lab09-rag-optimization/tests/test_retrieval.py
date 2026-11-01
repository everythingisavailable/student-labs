import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from rag_search import chunks_for,metrics,Index,load_model
class Tests(unittest.TestCase):
    def test_document_metrics_deduplicate(self):
        rows=[{'doc_id':x} for x in ['a','a','b']];self.assertEqual(metrics(rows,['b'])['mrr'],.5);self.assertEqual(metrics(rows,['a','b'])['recall'],1)
    def test_absent_excluded(self):self.assertIsNone(metrics([],[])['recall'])
    def test_chunk_coverage(self):
        doc={'doc_id':'x','text':' '.join(['слово']*200),'access_group':'students'};cs=chunks_for(doc,300,100);text=doc['text'];covered=set()
        for c in cs:self.assertEqual(text[c['start']:c['end']],c['text']);covered.update(range(c['start'],c['end']))
        self.assertTrue(all(i in covered for i,c in enumerate(text) if not c.isspace()))
    def test_acl_and_budget(self):
        index=Index(load_model(),role='students');self.assertFalse(any(c['doc_id'] in ['network','soc'] for c in index.chunks));r=index.retrieve('сервер модели',k=12,budget=1200);self.assertLessEqual(r['context_chars'],1200)
if __name__=='__main__':unittest.main()
