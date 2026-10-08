"""Compare actual student scores with saved judge scores after CSV completion."""
from pathlib import Path
import argparse,csv,json,statistics
from evaluate import CRITERIA,csvsave,save

def main():
 p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--human',type=Path);a=p.parse_args()
 source=a.human or a.run/'human_review_template.csv'
 with source.open(encoding='utf-8-sig',newline='') as f:human=list(csv.DictReader(f))
 with (a.run/'judge_comparison.csv').open(encoding='utf-8-sig',newline='') as f:judges={(x['version'],x['id']):json.loads(x['judge_scores']) for x in csv.DictReader(f)}
 if len(human)!=20 or len({(x['version'],x['id']) for x in human})!=20:raise SystemExit('Expected exactly 20 distinct human rows for the 10 pairs.')
 output=[]
 for x in human:
  if x['reviewer_type']!='human' or not all(x[k] in ('0','1','2') for k in CRITERIA) or x['hallucination'].lower() not in ('true','false'):
   raise SystemExit(f"Human review is not completed: {x['version']} {x['id']}. Use 0..2 and true/false.")
  key=(x['version'],x['id'])
  if key not in judges:raise SystemExit(f'No usable judge result for {key}')
  j=judges[key];scores=[int(x[k]) for k in CRITERIA];total=sum(scores)
  if x['total'] and int(x['total'])!=total:raise SystemExit(f'Incorrect total for {key}')
  output.append(dict(version=key[0],id=key[1],human_total=total,judge_total=sum(j[k] for k in CRITERIA),total_absolute_difference=abs(total-sum(j[k] for k in CRITERIA)),criteria_matches=sum(int(x[k])==j[k] for k in CRITERIA),criteria_absolute_difference=sum(abs(int(x[k])-j[k]) for k in CRITERIA),hallucination_matches=(x['hallucination'].lower()=='true')==j['hallucination']))
 csvsave(a.run/'human_judge_comparison.csv',output)
 summary=dict(n=len(output),criterion_agreement=sum(x['criteria_matches'] for x in output)/(4*len(output)),criterion_mae=sum(x['criteria_absolute_difference'] for x in output)/(4*len(output)),total_mae=statistics.mean(x['total_absolute_difference'] for x in output),hallucination_agreement=sum(x['hallucination_matches'] for x in output)/len(output))
 save(a.run/'human_judge_summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
