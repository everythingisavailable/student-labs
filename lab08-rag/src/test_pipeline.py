import unittest
from unittest.mock import patch
from rag import rag_answer,citation_check
from prompt import build_context
from retrieve import Retriever
import numpy as np

class Tests(unittest.TestCase):
    def test_citation_existence_not_entailment(self):
        self.assertEqual(citation_check('Факт [S1], [S9]',2)['invalid'],[9])
        self.assertFalse(citation_check('Недостаточно информации',2)['has_citations'])
        self.assertEqual(citation_check('Факт [S1, S9]',2)['invalid'],[9])
        self.assertEqual(citation_check('Факт [S1, S2]',2)['nonstandard_groups'],['[S1, S2]'])
    def test_real_retriever_acl_before_model_context(self):
        ret=Retriever.__new__(Retriever);ret.model=None
        ret.documents=[dict(id='secret',text='PRIVATE',source='hidden.txt',section='1',access_group='admins'),dict(id='public',text='PUBLIC',source='open.txt',section='1',access_group='students')]
        ret.vectors=np.array([[1.,0.],[.5,.5]])
        with patch('retrieve.encode',return_value=np.array([[1.,0.]])),patch('rag.llm_chat',return_value=dict(answer='PUBLIC [S1]',error=None)) as llm:
            result=rag_answer('test',ret,2,'students')
        self.assertNotIn('PRIVATE',result['context']);self.assertNotIn('hidden.txt',result['context']);self.assertEqual(len(result['retrieved']),1)
        self.assertIn('PUBLIC',llm.call_args.args[0][1]['content'])
    def test_unknown_role_is_rejected(self):
        ret=Retriever.__new__(Retriever);ret.documents=[]
        with self.assertRaises(ValueError):ret.retrieve('x',1,'guest')
    def test_external_llm_rejected(self):
        from llm import api_request
        with patch.dict('os.environ',{'LOCAL_BASE_URL':'https://example.com'}):
            with self.assertRaises(ValueError):api_request('/v1/models')
if __name__=='__main__':unittest.main()
