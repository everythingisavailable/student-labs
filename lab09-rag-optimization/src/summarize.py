"""Rebuild quality aggregates from saved reviews, not from keyword grading."""
from pathlib import Path
import json,csv,hashlib,statistics
P=Path(__file__).resolve().parents[1]
def main():
    rows=[json.loads(s) for s in (P/'results/generation.jsonl').read_text(encoding='utf-8').splitlines()]
    reviews=json.loads((P/'results/answer_review.json').read_text(encoding='utf-8'))
    lookup={(r['experiment_id'],r['question_id'],r['seed']):r for r in rows}
    for v in reviews:
        r=lookup[(v['experiment_id'],v['question_id'],v['seed'])]
        assert v['answer_sha256']==hashlib.sha256(r['answer'].encode()).hexdigest(),'Review mismatch'
    summary=[]
    for cfg in dict.fromkeys(r['experiment_id'] for r in rows):
        rr=[v for v in reviews if v['experiment_id']==cfg];ans=[v for v in rr if v['correctness'] is not None];absent=[v for v in rr if v['refusal_correct'] is not None];raw=[r for r in rows if r['experiment_id']==cfg]
        avg=lambda key:statistics.mean(v[key] for v in ans)
        summary.append({'config':cfg,'answerable_runs':len(ans),'absent_runs':len(absent),'correctness':avg('correctness'),'fully_correct':statistics.mean(v['correctness']==2 for v in ans),'grounded':avg('grounded'),'citations_correct':avg('citations_correct'),'refusal_correct':statistics.mean(v['refusal_correct'] for v in absent),'context_chars':statistics.mean(r['found']['context_chars'] for r in raw),'prompt_chars':statistics.mean(r['prompt_chars'] for r in raw),'latency_s':statistics.mean(r['llm_s'] for r in raw),'latency_sd_s':statistics.stdev(r['llm_s'] for r in raw),'prompt_tokens':statistics.mean(r['api_records'][0]['response']['usage']['prompt_tokens'] for r in raw)})
    (P/'results/quality_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (P/'results/quality_summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
    print('Verified answer hashes; rebuilt',len(summary),'quality summaries')
if __name__=='__main__':main()
