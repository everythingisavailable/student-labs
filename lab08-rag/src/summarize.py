"""Recompute metrics from original runs and saved per-answer reviews."""
import csv,statistics
from common import *
def main():
    run=ROOT/'results'/(ROOT/'results/latest.txt').read_text().strip()
    rows=readlines(run/'runs.jsonl');reviews=readjson(run/'quality_review.json');by_key={(r['question_id'],r['k']):r for r in reviews};summaries=[]
    for k in [2,4,8]:
        rr=[r for r in rows if r['k']==k];answerable=[r for r in rr if r['gold_ids']];absent=[r for r in rr if not r['gold_ids']]
        summaries.append(dict(k=k,calls=len(rr),recall=statistics.mean(r['retrieval_metrics']['recall'] for r in answerable),mrr=statistics.mean(r['retrieval_metrics']['mrr'] for r in answerable),mrr_at_k=statistics.mean(r['retrieval_metrics']['mrr_at_k'] for r in answerable),mean_quality=statistics.mean(by_key[(r['question_id'],k)]['total'] for r in rr),correct_refusal_percent=100*sum(by_key[(r['question_id'],k)]['correct_refusal'] is True for r in absent)/len(absent),context_chars=statistics.mean(r['context_chars'] for r in rr),latency_s=statistics.mean(r['total_s'] for r in rr)))
    save(ROOT/'results/recomputed_summary.json',summaries)
    print(json.dumps(summaries,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
