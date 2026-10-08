import json,unittest
from evaluate import parse,metrics

class EvaluationTests(unittest.TestCase):
    def test_native_contracts_and_no_json_repair(self):
        a='status: assessed\ncategory: normal\nrisk: low\nevidence: "пример"\nmissing_data: нет\nnext_action: сохранить'
        self.assertEqual(parse(a,'A','пример')['predicted'],'normal')
        b=dict(status='assessed',category='malware',risk='high',evidence=['пример'],missing_data=[],next_action='проверить')
        raw=json.dumps(b)
        self.assertEqual(parse(raw,'B','пример')['predicted'],'suspicious')
        self.assertEqual(parse('```json\n'+raw+'\n```','B','пример')['predicted'],'parse_error')
        b['evidence']='пример'
        self.assertFalse(parse(json.dumps(b),'B','пример')['format_ok'])
    def test_abstentions_and_parse_errors_stay_in_denominators(self):
        pairs=[('suspicious','suspicious'),('suspicious','abstain'),('suspicious','parse_error'),('normal','normal'),('normal','suspicious'),('normal','parse_error')]
        rows=[dict(expected=t,predicted=p,format_ok=p!='parse_error',json_ok=True,latency_s=i+1,input_tokens=10,output_tokens=20) for i,(t,p) in enumerate(pairs)]
        m=metrics(rows)
        self.assertAlmostEqual(m['accuracy'],2/6)
        self.assertAlmostEqual(m['precision'],1/2)
        self.assertAlmostEqual(m['recall'],1/3)
        self.assertAlmostEqual(m['f1'],.4)
        self.assertEqual(sum(sum(r.values()) for r in m['confusion_matrix'].values()),6)
        self.assertAlmostEqual(m['p95_latency_s'],5.75)

if __name__=='__main__':unittest.main()
