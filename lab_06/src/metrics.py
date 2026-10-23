"""Reproduce Lab6 tables and figures from immutable responses and explicit reviews."""
from pathlib import Path
import ast,csv,hashlib,json,re,statistics
ROOT=Path(__file__).resolve().parents[1]
RUNS={'local':'20261023_163927_utc_local','cloud':'20261023_200017_utc_cloud'}
TYPES={'t01':'Факты','t06':'Факты','t02':'Суммаризация','t07':'Суммаризация',
       **{x:'Классификация' for x in ['t03','t08','t11','t12']},
       **{x:'JSON' for x in ['t04','t09','t13','t14']},
       **{x:'Код и логика' for x in ['t05','t10','t15']},
       **{f't{i}':'Анализ риска' for i in range(16,21)}}

def write_json(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def csv_out(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def reviewed_function(answer,test_id):
    """Only reviewed hashlib/re snippets; no arbitrary generated code execution."""
    code=re.search(r'```python\s*\n(.*?)```',answer,re.S).group(1)
    tree=ast.parse(code)
    allowed=(ast.Module,ast.Import,ast.alias,ast.FunctionDef,ast.arguments,ast.arg,
             ast.Expr,ast.Constant,ast.Assign,ast.Name,ast.Load,ast.Store,ast.Call,
             ast.Attribute,ast.Return)
    for n in ast.walk(tree):
        if not isinstance(n,allowed):raise ValueError('Unsupported code node')
        if isinstance(n,ast.Import) and any(a.name not in ['re','hashlib'] for a in n.names):raise ValueError('Unsupported import')
        if isinstance(n,ast.Attribute) and n.attr not in ['search','sha256','encode','hexdigest']:raise ValueError('Unsupported attribute')
        if isinstance(n,ast.Name) and n.id.startswith('__'):raise ValueError('Unsupported name')
    funcs=[n.name for n in tree.body if isinstance(n,ast.FunctionDef)]
    def safe_import(name,*args):
        if name not in ['re','hashlib']:raise ValueError('Unsupported import')
        return __import__(name)
    ns={'__builtins__':{'__import__':safe_import,'bool':bool}}
    exec(compile(tree,'<reviewed-pure-function>','exec'),ns)
    return ns['contains_ipv4' if test_id=='t10' else funcs[0]]

def objective(r):
    answer=r['answer'];s=answer.strip();tid=r['test_id'];checks={};fmt=None
    if tid in ['t04','t09','t13','t14']:
        try:obj=json.loads(s);fmt=isinstance(obj,dict)
        except ValueError:obj=None;fmt=False
        clean=re.sub(r'^```(?:json)?\s*\n|\n```$','',s).strip()
        try:obj=json.loads(clean)
        except ValueError:obj=None
        checks['strict_json']=fmt
        if tid=='t13':checks['values_after_optional_fence_removal']=obj=={'count':7,'event':'login_failure'}
        if tid=='t14':checks['values_after_optional_fence_removal']=obj=={'service':'backup','status':'success'}
    if tid in ['t11','t12','t15']:
        fmt=s=={'t11':'normal','t12':'phishing','t15':'3'}[tid];checks['exact_match']=fmt
    if tid=='t01':checks['word_count']=len(s.split());fmt=checks['word_count']<=120
    if tid in ['t02','t07']:
        checks['numbered_points']=len(re.findall(r'^\d+\.\s',s,re.M));fmt=checks['numbered_points']==(5 if tid=='t02' else 3)
    if tid=='t06':checks['sentence_count']=len(re.findall(r'[.!?](?:\s|$)',s));fmt=checks['sentence_count']==5
    if tid in ['t05','t10']:
        f=reviewed_function(answer,tid)
        if tid=='t05':examples=[('',hashlib.sha256(b'').hexdigest()),('abc',hashlib.sha256(b'abc').hexdigest()),('Привет',hashlib.sha256('Привет'.encode()).hexdigest())]
        else:examples=[('IP 192.168.1.1',True),('0.0.0.0',True),('255.255.255.255',True),('text without address',False),('256.2.3.4',False),('1.2.3',False),('1.2.3.4.5',False),('999.1.2.3.4',False),('x1.2.3.4y',False)]
        checks['code_cases']=[{'input':x,'expected':expected,'actual':f(x),'pass':f(x)==expected} for x,expected in examples]
    return fmt,checks

def main():
    out=ROOT/'results';reviews=json.loads((out/'quality_review.json').read_text(encoding='utf-8'))
    review={(r['backend'],r['test_id'],r['repeat']):r for r in reviews}
    allrows=[];summaries=[];pertest=[];resources={};objective_rows=[]
    for backend,run in RUNS.items():
        rows=[json.loads(x) for x in (out/run/'raw_results.jsonl').read_text(encoding='utf-8').splitlines()]
        assert len(rows)==30 and len({r['test_id'] for r in rows})==20
        for r in rows:
            q=review[(backend,r['test_id'],r['repeat'])]
            assert q['answer_sha256']==hashlib.sha256(r['answer'].encode()).hexdigest()
            fmt,checks=objective(r);success=q['content_score']==2 and fmt is not False
            row={'backend':backend,'model':r['requested_model'],'test_id':r['test_id'],'repeat':r['repeat'],'type':TYPES[r['test_id']],
                 'latency_s':r['latency_s'],'input_tokens':r['input_tokens'],'output_tokens':r['output_tokens'],
                 'api_total_tokens':r['api_response']['usage']['total_tokens'],'effective_output_tokens_s':r['output_tokens_per_total_second'],
                 'content_score':q['content_score'],'format_pass':fmt,'fully_correct':success,'error':r['error'],
                 'prompt':r['messages'][1]['content'],'answer':r['answer'],'review_reason':q['reason']}
            allrows.append(row);objective_rows.append({'backend':backend,'test_id':r['test_id'],'repeat':r['repeat'],'checks':checks})
        rs=[r for r in allrows if r['backend']==backend];meta=json.loads((out/run/'environment_resources.json').read_text())
        for tid in sorted({r['test_id'] for r in rs}):
            ts=[r for r in rs if r['test_id']==tid];lat=[r['latency_s'] for r in ts]
            pertest.append({'backend':backend,'test_id':tid,'type':TYPES[tid],'n':len(ts),'mean_score':statistics.mean(r['content_score'] for r in ts),
                            'fully_correct_fraction':statistics.mean(r['fully_correct'] for r in ts),'latency_mean_s':statistics.mean(lat),
                            'latency_stdev_s':statistics.stdev(lat) if len(lat)>1 else None,'latency_min_s':min(lat),'latency_max_s':max(lat),
                            'unique_answers':len({r['answer'] for r in ts})})
        ts=[r for r in pertest if r['backend']==backend];lat=[r['latency_s'] for r in rs]
        summaries.append({'backend':backend,'model':rs[0]['model'],'calls':len(rs),'errors':sum(bool(r['error']) for r in rs),
                          'score_macro_20':statistics.mean(r['mean_score'] for r in ts),'score_micro_30':statistics.mean(r['content_score'] for r in rs),
                          'fully_correct_macro_20':statistics.mean(r['fully_correct_fraction'] for r in ts),
                          'fully_correct_micro_30':statistics.mean(r['fully_correct'] for r in rs),
                          'latency_mean_s':statistics.mean(lat),'latency_median_s':statistics.median(lat),'latency_stdev_s':statistics.stdev(lat),
                          'latency_min_s':min(lat),'latency_max_s':max(lat),'input_tokens_sum':sum(r['input_tokens'] for r in rs),
                          'output_tokens_sum':sum(r['output_tokens'] for r in rs),'api_total_tokens_sum':sum(r['api_total_tokens'] for r in rs),
                          'effective_output_tokens_per_second':sum(r['output_tokens'] for r in rs)/sum(lat),
                          'completed_requests_per_minute':meta['completed_requests_per_minute'],
                          'strict_json_success':sum(r['format_pass'] is True for r in rs if r['type']=='JSON'),'json_tests':4})
        resources[backend]={'sample_count':len(meta['samples']),'before':meta['before'],'scope':'Whole local workstation, not model-only; cloud host hardware is not measured.'}
        for metric in ['cpu_percent','ram_used_gib','vram_used_mib','gpu_percent']:
            vals=[s[metric] for s in meta['samples'] if metric in s]
            resources[backend][metric]={'mean':statistics.mean(vals),'min':min(vals),'max':max(vals)} if vals else None
    lr=[r for r in allrows if r['backend']=='local'];cr=[r for r in allrows if r['backend']=='cloud']
    for a,b in zip(lr,cr):assert (a['test_id'],a['repeat'],a['prompt'])==(b['test_id'],b['repeat'],b['prompt'])
    rawl=[json.loads(x) for x in (out/RUNS['local']/'raw_results.jsonl').read_text(encoding='utf-8').splitlines()]
    rawc=[json.loads(x) for x in (out/RUNS['cloud']/'raw_results.jsonl').read_text(encoding='utf-8').splitlines()]
    assert all(a['messages']==b['messages'] and a['temperature']==b['temperature'] and a['max_tokens']==b['max_tokens'] for a,b in zip(rawl,rawc))
    cloud=summaries[1];avg=cloud['api_total_tokens_sum']/30
    economics={'date':'2026-10-24 Asia/Omsk','source':'https://developers.sber.ru/docs/ru/gigachat/tariffs/individual-tariffs',
               'measured_tokens':cloud['api_total_tokens_sum'],'tokens_per_request':avg,'balance_decrease':250000000-249996098,
               'freemium_lite_tokens_initial':250000000,'freemium_validity_months':12,
               'conditions':'Freemium within remaining allowance and validity, educational personal use, one sequential stream. No future availability guarantee.',
               'legacy_paid_comparison':'Illustrative allocation at 1300 RUB / 20,000,000 tokens for eligible existing customers, not an offer to this new account. Whole package costs 1300 RUB; validity one month.',
               'scenarios':[{'requests':n,'estimated_tokens':avg*n,'freemium_cash_rub':0,'legacy_paid_allocated_rub':avg*n*1300/20000000} for n in [30,1000,100000]]}
    assert economics['measured_tokens']==economics['balance_decrease']
    csv_out(out/'raw_results.csv',allrows);csv_out(out/'summary.csv',summaries);csv_out(out/'per_test_summary.csv',pertest)
    write_json(out/'summary.json',summaries);write_json(out/'resource_summary.json',resources);write_json(out/'objective_checks.json',objective_rows);write_json(out/'economics.json',economics)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
    figs=out/'figures';figs.mkdir(exist_ok=True)
    labels=['Факты','Суммаризация','Классификация','JSON','Код и логика','Анализ риска']
    fig,ax=plt.subplots(figsize=(9,4.2))
    for j,backend in enumerate(RUNS):
        vals=[statistics.mean(r['mean_score'] for r in pertest if r['backend']==backend and r['type']==kind) for kind in labels]
        ax.bar([i+(j-.5)*.36 for i in range(6)],vals,.36,label='Gemma локально' if j==0 else 'GigaChat облако')
    ax.set_xticks(range(6),labels,rotation=12);ax.set_ylim(0,2.3);ax.set_ylabel('Содержательная оценка 0–2');ax.legend();ax.grid(axis='y',alpha=.2);fig.tight_layout();fig.savefig(figs/'quality.png',dpi=180);plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,4))
    ax.boxplot([[r['latency_s'] for r in lr],[r['latency_s'] for r in cr]],tick_labels=['Gemma локально','GigaChat облако'],showmeans=True)
    for i,rs in enumerate([lr,cr],1):ax.scatter([i+((j%7)-3)*.025 for j in range(len(rs))],[r['latency_s'] for r in rs],s=12,alpha=.55)
    ax.set_ylabel('Полная задержка, с');ax.grid(axis='y',alpha=.2);fig.tight_layout();fig.savefig(figs/'latency.png',dpi=180);plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,3.5))
    bars=ax.bar(['Gemma локально','GigaChat облако'],[s['effective_output_tokens_per_second'] for s in summaries],color=['#3d70a0','#d38a35'])
    ax.bar_label(bars,fmt='%.1f');ax.set_ylabel('Выходные токены / полное время, токен/с');ax.set_ylim(0,max(s['effective_output_tokens_per_second'] for s in summaries)*1.18);fig.tight_layout();fig.savefig(figs/'effective_speed.png',dpi=180);plt.close(fig)
    print(json.dumps({'summary':summaries,'resources':resources,'economics':economics},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
