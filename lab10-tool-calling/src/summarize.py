"""Aggregate trace metrics and saved semantic reviews; does not grade new answers."""
from pathlib import Path
import json,csv,hashlib,statistics,collections,sys
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def csvfile(p,rows):
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def mean(xs):return statistics.mean(xs) if xs else None
def ratio(a,b):return a/b if b else None
def summarize(root):
    rows=[json.loads(s) for s in (root/'results/runs.jsonl').read_text(encoding='utf-8').splitlines()]
    reviews=read(root/'results/quality_review.json');assert len(rows)==len(reviews)
    for i,(r,v) in enumerate(zip(rows,reviews)):
        assert v['row_index']==i and v['case_id']==r['case_id'] and v['seed']==r['seed']
        assert v['answer_sha256']==hashlib.sha256(r['answer'].encode()).hexdigest(),'Review belongs to different answer'
    agent='max_rounds' in reviews[0];key='max_rounds' if agent else 'mode';groups=[2,6] if agent else ['without_tools','with_tools'];metrics=[]
    for group in groups:
        pairs=[(r,v) for r,v in zip(rows,reviews) if v[key]==group];rr=[r for r,v in pairs];vv=[v for r,v in pairs]
        calls=sum(v['proposed_calls'] for v in vv);unsafe=sum(v['unsafe_attempts'] for v in vv)
        m={key:group,'n':len(rr),'latency_s':mean([r['latency_s'] for r in rr]),'latency_sd_s':statistics.stdev(r['latency_s'] for r in rr),'unsafe_attempts':unsafe,'unsafe_rejection':ratio(sum(v['unsafe_rejected'] for v in vv),unsafe),'proposed_calls':calls,'valid_calls':sum(v['valid_calls'] for v in vv)}
        if agent:m.update(task_success=mean([v['task_success'] for v in vv]),valid_call_rate=ratio(m['valid_calls'],calls),rounds=mean([r['rounds'] for r in rr]),calls=mean([r['calls'] for r in rr]),abnormal_termination=mean([r['status']!='completed' for r in rr]),statuses=dict(collections.Counter(r['status'] for r in rr)))
        else:m.update(task_completion=mean([v['task_success'] for v in vv]),selection_accuracy=mean([v['selection_correct'] for v in vv if v['selection_correct'] is not None]),argument_validity=ratio(m['valid_calls'],calls))
        metrics.append(m)
    save(root/'results/metrics.json',metrics);csvfile(root/'results/metrics.csv',metrics)
    flat=[{'case_id':r['case_id'],'seed':r['seed'],key:v[key],'status':r['status'],'tools':'; '.join(t['name'] for t in r['trace']),'task_success':v['task_success'],'latency_s':r['latency_s'],'comment':v['reason']} for r,v in zip(rows,reviews)]
    csvfile(root/'results/test_cases.csv',flat)
    if not agent:
        cases=[]
        for cid in dict.fromkeys(r['case_id'] for r in rows):
            idx=[i for i,r in enumerate(rows) if r['case_id']==cid];cases.append({'case_id':cid,'without_success':sum(reviews[i]['task_success'] for i in idx if rows[i]['mode']=='without_tools'),'with_success':sum(reviews[i]['task_success'] for i in idx if rows[i]['mode']=='with_tools'),'tools':'; '.join(sorted({t['name'] for i in idx for t in rows[i]['trace']})) or 'нет'})
        save(root/'results/case_summary.json',cases)
    for success,name in [(True,'trace_success.json'),(False,'trace_failure.json')]:
        pair=next((r,v) for r,v in zip(rows,reviews) if v['task_success']==success and (agent or r['mode']=='with_tools'))
        save(root/'results'/name,{'run':pair[0],'review':pair[1]})
    print(json.dumps(metrics,ensure_ascii=False,indent=2))
if __name__=='__main__':summarize(ROOT)
