import unittest
from common import metrics,ranked
from evaluate import gold_for_chunks
import numpy as np
class CoreTests(unittest.TestCase):
 def test_metrics_multiple_gold(self):
  docs=[{'id':x} for x in 'abcd'];m=metrics([0,1,2,3],docs,['b','d'],3)
  self.assertAlmostEqual(m['precision'],1/3);self.assertEqual(m['recall'],.5);self.assertEqual(m['mrr'],.5)
 def test_acl_filters_before_top_k(self):
  docs=[dict(id='hidden',access_group='admins'),dict(id='visible',access_group='students')]
  self.assertEqual(ranked(np.array([1.,.1]),docs,'students').tolist(),[1])
  with self.assertRaises(ValueError):ranked(np.array([1.,.1]),docs,'unknown')
 def test_gold_half_overlap(self):
  base=[dict(id='a',source='x',start=0,end=100)]
  chunks=[dict(id='short',source='x',start=51,end=110),dict(id='half',source='x',start=50,end=110),dict(id='foreign',source='y',start=0,end=100)]
  self.assertEqual(gold_for_chunks(dict(relevant_ids=['a']),chunks,base),['half'])
if __name__=='__main__':unittest.main()
