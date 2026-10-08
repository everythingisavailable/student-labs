"""Reproducible prompt comparison. Run --check before making API calls."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from datetime import datetime
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {'status', 'category', 'risk', 'evidence', 'missing_data', 'next_action'}
CRITERIA = ['task', 'factual_caution', 'format', 'completeness', 'missing_data_handling', 'rule_resistance']


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def validate(answer, source, individual=False):
    """Validate exact JSON, types, enums and quoted evidence; not semantic quality."""
    errors = []
    try:
        obj = json.loads(answer)
    except (ValueError, TypeError):
        return ['invalid_json']
    fields = (FIELDS - {'category', 'risk'}) | {'verdict'} if individual else FIELDS
    if not isinstance(obj, dict) or set(obj) != fields:
        return ['wrong_fields']
    if obj['status'] not in ('assessed', 'insufficient_data'):
        errors.append('invalid_status')
    if individual:
        if obj['verdict'] not in ('phishing_signs', 'no_obvious_signs', 'unknown'):
            errors.append('invalid_verdict')
    else:
        if obj['category'] not in ('normal', 'authentication_anomaly', 'phishing', 'malware', 'data_exposure', 'unknown'):
            errors.append('invalid_category')
        if obj['risk'] not in ('low', 'medium', 'high', 'critical', 'unknown'):
            errors.append('invalid_risk')
    for field in ('evidence', 'missing_data'):
        if not isinstance(obj[field], list) or any(not isinstance(v, str) or not v.strip() for v in obj[field]):
            errors.append('invalid_' + field)
    if isinstance(obj['evidence'], list) and any(isinstance(v, str) and v not in source for v in obj['evidence']):
        errors.append('evidence_not_exact_quote')
    if not isinstance(obj['next_action'], str) or not obj['next_action'].strip():
        errors.append('invalid_next_action')
    if obj['status'] == 'insufficient_data' and not obj['missing_data']:
        errors.append('missing_data_empty')
    return errors


def write_csv(path, rows, fields):
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items()} for row in rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Validate inputs without API calls')
    parser.add_argument('--versions', nargs='+', default=['v1', 'v2', 'v3', 'v4_json', 'individual'], choices=['v1', 'v2', 'v3', 'v4_json', 'individual'])
    args = parser.parse_args()
    tests = read_json(ROOT/'data/tests.json')
    individual = read_json(ROOT/'data/individual_tests.json')
    config = read_json(ROOT/'config/experiment.json')
    assert len(tests) >= 10 and len(individual) >= 5
    assert len({x['id'] for x in tests + individual}) == len(tests + individual)
    jobs = []
    for version in args.versions:
        name = 'individual.txt' if version == 'individual' else f'prompt_{version}.txt'
        prompt = (ROOT/'prompts'/name).read_text(encoding='utf-8')
        for case in individual if version == 'individual' else tests:
            jobs.append((version, prompt, case))
    print(f'Prepared {len(jobs)} calls; model is fixed for the entire run.')
    if args.check:
        print('Input check passed. No API requests made.')
        return
    from dotenv import load_dotenv
    from openai import OpenAI
    load_dotenv(ROOT/'.env')
    model = os.getenv('LLM_MODEL', 'google/gemma-3n-e4b')
    url = os.getenv('LLM_BASE_URL', 'http://localhost:1234/v1')
    key = os.getenv('LLM_API_KEY', 'lm-studio')
    client = OpenAI(base_url=url, api_key=key, timeout=config['timeout'], max_retries=0)
    try:
        available = {m.id for m in client.models.list().data}
    except Exception as exc:
        raise SystemExit(f'API preflight failed: {type(exc).__name__}. Start LM Studio server and check .env.') from None
    if model not in available:
        raise SystemExit('Configured model not found. Set LLM_MODEL to the exact identifier displayed by LM Studio.')
    out = ROOT/'results'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    out.mkdir(parents=True)
    for directory in ('prompts', 'data', 'config'):
        shutil.copytree(ROOT/directory, out/directory)
    metadata = dict(model=model, temperature=config['temperature'], max_tokens=config['max_tokens'], versions=args.versions,
                    started_at=datetime.now().astimezone().isoformat(), source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    rows = []
    for number, (version, prompt, case) in enumerate(jobs, 1):
        started = time.perf_counter()
        row = dict(version=version, test_id=case['id'], kind=case['kind'], model=model, system_prompt=prompt,
                   input=case['input'], temperature=config['temperature'], max_tokens=config['max_tokens'],
                   answer='', latency_s=0, finish_reason='', prompt_tokens=None, completion_tokens=None, error='', validation=[])
        try:
            response = client.chat.completions.create(model=model, messages=[{'role':'system','content':prompt}, {'role':'user','content':case['input']}],
                                                      temperature=config['temperature'], max_tokens=config['max_tokens'])
            row['answer'] = response.choices[0].message.content or ''
            row['finish_reason'] = response.choices[0].finish_reason
            if response.usage:
                row['prompt_tokens'] = response.usage.prompt_tokens
                row['completion_tokens'] = response.usage.completion_tokens
            if not row['answer'].strip():
                row['error'] = 'empty_answer'
            if version in ('v4_json', 'individual'):
                row['validation'] = validate(row['answer'], case['input'], version == 'individual')
        except Exception as exc:
            row['error'] = type(exc).__name__  # Do not export exception bodies or credentials.
        row['latency_s'] = round(time.perf_counter()-started, 3)
        rows.append(row)
        with (out/'responses.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False)+'\n')
        print(f"{number}/{len(jobs)} {version} {case['id']}: {row['error'] or 'received'}, {row['latency_s']} s", flush=True)
        (out/'responses.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    write_csv(out/'responses.csv', rows, list(rows[0]))
    ratings = [dict(version=r['version'], test_id=r['test_id'], **{k:'' for k in CRITERIA}, comment='') for r in rows]
    write_csv(out/'ratings.csv', ratings, list(ratings[0]))
    groups = defaultdict(list)
    for row in rows:
        groups[row['version']].append(row)
    summary = []
    for version, group in groups.items():
        ok = [r for r in group if not r['error']]
        summary.append(dict(version=version, calls=len(group), successful=len(ok), mean_latency_s=round(sum(r['latency_s'] for r in ok)/len(ok),3) if ok else None,
                            truncated=sum(r['finish_reason']=='length' for r in group),
                            json_and_schema_pass=sum(not r['validation'] and not r['error'] for r in group) if version in ('v4_json','individual') else None))
    write_csv(out/'summary.csv', summary, list(summary[0]))
    print('Saved:',out)
    print('Semantic scores remain empty. Review each answer and fill ratings.csv; automatic format checks are not quality scores.')


if __name__ == '__main__':
    main()
