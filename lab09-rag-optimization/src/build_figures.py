from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
ROOT=Path(__file__).resolve().parents[2]
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':150})
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def finish(fig,p):fig.tight_layout();fig.savefig(p,bbox_inches='tight');plt.close(fig)
for folder,labels in [('lab09-rag-optimization',['Документы\nи ACL','Фрагменты\nи эмбеддинги','Dense / TF-IDF\nRRF / rerank','Контекст\nс ID','LLM и оценка\nпо источникам']),('lab10-tool-calling',['Запрос\nпользователя','Модель\ntool_calls','Диспетчер\nпроверка прав','Функции\nтолько чтение','Модель\nитог без tools']),('lab11-agent-loop',['Цель\nи история','Модель\nвыбор действия','Политика\nлимиты / ACL','Инструменты\nи наблюдения','Итог или\nследующий шаг'])]:
    p=ROOT/folder/'figures';p.mkdir(exist_ok=True);fig,ax=plt.subplots(figsize=(10,2.2));ax.set_xlim(0,10);ax.set_ylim(-.25,2);ax.axis('off')
    for i,label in enumerate(labels):
        x=.08+i*2;box=FancyBboxPatch((x,.65),1.72,.9,boxstyle='round,pad=0.05',facecolor='#edf2f7',edgecolor='#46627e');ax.add_patch(box);ax.text(x+.86,1.1,label,ha='center',va='center',fontsize=9)
        if i<4:ax.annotate('',xy=(x+1.96,1.1),xytext=(x+1.77,1.1),arrowprops={'arrowstyle':'->','color':'#46627e'})
    if folder.startswith('lab11'):
        ax.annotate('',xy=(2.94,.55),xytext=(8.94,.55),arrowprops={'arrowstyle':'->','connectionstyle':'bar,fraction=-.06','color':'#46627e'});ax.text(5.9,-.12,'Повтор с наблюдением, пока не получен итог или не достигнут лимит',ha='center',fontsize=8)
    finish(fig,p/'architecture.png')
p=ROOT/'lab09-rag-optimization';search=read(p/'results/summary.json');quality=read(p/'results/quality_summary.json')
data=[next(r for r in search if r['id']==f'dense_{size}_100_k4') for size in [300,600,1200]]
fig,ax=plt.subplots(figsize=(7,3.6));xs=[r['chunk_size'] for r in data]
for key,title in [('hit','Hit@4'),('recall','Recall@4'),('mrr','MRR')]:ax.plot(xs,[r[key] for r in data],marker='o',label=title)
ax.set(xlabel='Размер фрагмента, символов',ylabel='Метрика',ylim=(.6,1.05),xticks=xs);ax.grid(alpha=.2);ax.legend();finish(fig,p/'figures/metric_by_chunk_size.png')
fig,ax=plt.subplots(figsize=(7,3.8));short=['300 / k4','600 / k4','1200 / k4','600 / k2','600 / k8','hybrid / k4']
for i,(r,label) in enumerate(zip(quality,short)):
    ax.scatter(r['context_chars'],r['correctness'],s=55);ax.annotate(label,(r['context_chars'],r['correctness']),xytext=(6,8 if i%2 else -18),textcoords='offset points',fontsize=8)
ax.set(xlabel='Средний контекст, символов, все 20 вопросов',ylabel='Корректность 0–2, 15 ответимых вопросов',ylim=(1.3,1.85));ax.grid(alpha=.2);finish(fig,p/'figures/quality_vs_context.png')
for n,folder in [(10,'lab10-tool-calling'),(11,'lab11-agent-loop')]:
    p=ROOT/folder;f=p/'results/metrics.json'
    if not f.exists():continue
    m=read(f)
    if n==10:
        fig,ax=plt.subplots(figsize=(7,3.5));labels=['Без инструментов','С инструментами'];ax.bar(labels,[100*r['task_completion'] for r in m],color=['#a4b2c0','#315d7e']);ax.set(ylabel='Успешные задачи, %',ylim=(0,105));finish(fig,p/'figures/task_completion.png')
    else:
        fig,ax=plt.subplots(figsize=(6.5,3.5));labels=[str(r['max_rounds']) for r in m];ax.bar(labels,[100*r['task_success'] for r in m],color='#315d7e');ax.set(xlabel='Лимит раундов',ylabel='Успешные задачи, %',ylim=(0,105));finish(fig,p/'figures/success_by_rounds.png')
        fig,axes=plt.subplots(1,2,figsize=(8,3.5));axes[0].bar(labels,[r['latency_s'] for r in m],color='#315d7e');axes[0].set(xlabel='Лимит раундов',ylabel='Среднее время, с');axes[1].bar(labels,[r['calls'] for r in m],color='#7198b4');axes[1].set(xlabel='Лимит раундов',ylabel='Среднее число попыток');finish(fig,p/'figures/latency_and_calls.png')
print('Figures generated from measurements')
