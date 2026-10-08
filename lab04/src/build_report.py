"""Rebuild derived analysis and Markdown report from saved records; no model calls."""
from pathlib import Path
import csv,json,re,statistics,sys
from evaluate import csvsave,save,CRITERIA
ROOT=Path(__file__).resolve().parents[1]

def main():
    run=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'results/20261008_131156_utc'
    read=lambda name:json.loads((run/name).read_text(encoding='utf-8'))
    def csvread(name):
        with (run/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
    rows=read('responses.json');primary=[r for r in rows if r['repeat']==0];metrics=read('metrics.json');reviews=csvread('assistant_review.csv');repeat_reviews=csvread('repeat_review.csv');cfg=read('config/experiment.json');tests=read('data/tests.json')
    judges=[json.loads(s) for s in (run/'judge.jsonl').read_text(encoding='utf-8').splitlines()] if (run/'judge.jsonl').exists() else []
    comparison=[]
    # Transparent secondary normalization of judge scores ONLY. Target-model strict metrics unchanged.
    for j in judges:
        raw=j['raw'].strip();normalized=raw
        if raw.startswith('```') and raw.endswith('```'):
            normalized=re.sub(r'^```(?:json)?\s*','',raw,flags=re.I);normalized=re.sub(r'\s*```$','',normalized)
        try:
            p=json.loads(normalized);valid=all(type(p[k]) is int and 0<=p[k]<=2 for k in CRITERIA) and type(p['hallucination']) is bool and isinstance(p['explanations'],dict) and all(isinstance(p['explanations'][k],str) and p['explanations'][k].strip() for k in CRITERIA)
        except (ValueError,KeyError,TypeError):p=None;valid=False
        if not valid:continue
        a=next(x for x in reviews if x['version']==j['version'] and x['id']==j['id'])
        comparison.append(dict(version=j['version'],id=j['id'],assistant_total=int(a['total']),judge_total=sum(p[k] for k in CRITERIA),absolute_total_difference=abs(int(a['total'])-sum(p[k] for k in CRITERIA)),matching_criteria=sum(int(a[k])==p[k] for k in CRITERIA),criteria_absolute_difference=sum(abs(int(a[k])-p[k]) for k in CRITERIA),assistant_hallucination=a['hallucination']=='True',judge_hallucination=p['hallucination'],strict_judge_format_ok=j['judge_format_ok'],normalized_fences=raw!=normalized,judge_scores=p))
    csvsave(run/'judge_comparison.csv',comparison)
    summary={'n_judge_calls':len(judges),'strict_valid':sum(j['judge_format_ok'] for j in judges),'usable_after_explicit_fence_normalization':len(comparison),'mean_absolute_total_difference':statistics.mean(x['absolute_total_difference'] for x in comparison) if comparison else None,'criterion_agreement':sum(x['matching_criteria'] for x in comparison)/(4*len(comparison)) if comparison else None,'criterion_mae':sum(x['criteria_absolute_difference'] for x in comparison)/(4*len(comparison)) if comparison else None,'hallucination_agreement':sum(x['assistant_hallucination']==x['judge_hallucination'] for x in comparison)/len(comparison) if comparison else None}
    save(run/'judge_summary.json',summary)
    groups=[]
    for v in ['A','B']:
        for d in ['easy','hard','boundary']:
            rs=[r for r in primary if r['version']==v and r['difficulty']==d]
            groups.append(dict(version=v,difficulty=d,n=len(rs),correct=sum(r['predicted']==r['expected'] for r in rs),false_positive=sum(r['expected']=='normal' and r['predicted']=='suspicious' for r in rs),abstain=sum(r['predicted']=='abstain' for r in rs),format_errors=sum(not r['format_ok'] for r in rs)))
    csvsave(run/'difficulty.csv',groups)
    stability=read('stability.json')
    for s in stability:
        base=next(x for x in reviews if x['version']==s['version'] and x['id']==s['id']);rep=[x for x in repeat_reviews if x['version']==s['version'] and x['id']==s['id']]
        scores=[int(base['total'])]+[int(x['total']) for x in rep];s.update(assistant_content_scores=scores,score_min=min(scores),score_max=max(scores))
    csvsave(run/'stability_with_review.csv',stability)
    out=[]
    def p(s=''):out.append(s)
    def heading(s):p('\n## '+s+'\n')
    def table(headers,data):
        block=['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']
        for row in data:block.append('| '+' | '.join(str(x).replace('|','/').replace('\n',' ') for x in row)+' |')
        p('\n'.join(block))
    p('# Лабораторная работа 4\n\nОценка качества больших языковых моделей\n')
    heading('Цель и итог эксперимента')
    p('Построен воспроизводимый мини-бенчмарк первичной классификации ИБ-событий. На одной локальной модели сравниваются два исходных промпта ЛР3 без изменений. При строгой обработке ответов вариант A дал F1 0,811, B — 0,316. Основная причина низкого результата B — запрещенное обрамление JSON в Markdown. A обнаружил все 15 положительных событий, но дал 7 ложных тревог; ни один вариант не рекомендуется для автономных решений.')
    p('Выполнено 60 основных вызовов и 30 дополнительных повторов. Оценка 10 пар объяснений подготовлена ассистентом отдельно от локального judge. Это не ручная оценка студента: human_review_template.csv оставлен для самостоятельной проверки, и сравнение human vs LLM до ее проведения не заявляется.')
    heading('Набор данных и эталон')
    p('Набор tests.json содержит 30 новых синтетических событий: по 10 обычных, сложных и граничных; 15 normal и 15 suspicious. Сценарий индивидуального задания — первичная классификация ИБ-событий. Используется тот же набор для основной и индивидуальной частей. Подтвержденные штатные операции относятся к normal; authentication_anomaly, phishing, malware и data_exposure — к suspicious. unknown преобразуется в abstain, а не в normal.')
    p('События включают разрешенное сканирование, VPN, ложное срабатывание, подтвержденный фишинг, вредоносные файлы без доказанного исполнения и инструкции внутри журналов. У всех 30 событий есть данные для эталонной категории. Неизвестный ущерб не разрешает модели выдумывать заражение. Входы не копируют few-shot примеры, но относятся к тем же темам. Это авторский учебный набор без независимой внешней валидации.')
    p('Эталоны, основная метрика, два исторических промпта, 10 пар для оценки и 5 сложных примеров для повторов зафиксированы до вызовов. После просмотра ответов промпты и эталоны не менялись. Полные входы, эталонные категории и основания находятся в data/tests.json; снимок включен в папку запуска.')
    heading('Модель промпты и параметры')
    table(['Параметр','Значение'],[['Дата','8 октября 2026 года; каталог '+run.name],['Модель A и B',cfg['model']+'; GGUF Q4_K_M'],['Контекст','8192 токена по локальному API'],['Промпт A','ЛР3 prompt_v2.txt; шесть текстовых полей'],['Промпт B','ЛР3 prompt_v4_json.txt; JSON, few-shot и уточнения'],['Общие настройки','temperature=0.2; max_tokens=700; seed не задан'],['API','Локальный LM Studio; /v1/chat/completions'],['Повторы','T21, T23, T24, T29, T30; по 3 дополнительных'],['Судья',cfg['judge_model']+'; Q3_K_M'],['Настройки судьи','temperature=0; max_tokens=1600; отдельные запросы'],['Стоимость','Не рассчитывалась; тариф/электроэнергия не заданы']])
    p('Промпты классификатора скопированы побайтово из ЛР3; SHA256 записаны в prompts/provenance.json. Новым является только промпт оценщика judge_v1, так как в ЛР3 отдельного судьи не было. Пользовательский шаблон одинаков: «Учебное событие для анализа:» и исходный текст. Эталон модели-классификатору не передавался. Судья получает эталон, ответ и соответствующий исходный промпт, но не оценки ассистента.')
    p('Запросы основных вариантов чередовались A/B для каждого события; после 60 вызовов выполнялись повторы, затем judge. Новая сессия на каждый запрос, без истории диалога и без автоматических ретраев. Полная аппаратная конфигурация и версия серверного runtime не зафиксированы, поэтому абсолютную скорость нельзя переносить на другие компьютеры. Конфигурации отличаются длиной промпта; контролируемым фактором является весь промпт, а не отдельно few-shot.')
    p('temperature и max_tokens переданы явно; остальные параметры сэмплирования наследуются от серверных настроек и не зафиксированы отдельно. По этой причине сохраненные материалы обеспечивают повторяемую процедуру, но не гарантируют побайтовое повторение генерации.')
    heading('Правила расчета метрик')
    p('Основная метрика — F1 класса suspicious. Дополнительно оценивается Recall: недоставленная тревога опаснее лишней проверки. Accuracy = число совпадений / 30; Precision = TP / (TP + FP); Recall = TP / 15; F1 = 2PR / (P + R). abstain и parse_error остаются в знаменателях, положительные ошибки уменьшают Recall. Они показаны отдельно от обычного FN в матрице 2×4. Нулевой знаменатель Precision трактуется как 0.')
    p('Format compliance — доля ответов, удовлетворяющих собственному контракту варианта. Для A проверяются ровно шесть заголовков, порядок и значения; для B — строгий JSON, точные поля и типы. Ограничение 180 слов проверяется приближенно через разделение по пробелам. Дословность evidence проверяется отдельно и входит в оценку инструкции; синтаксическая валидность не означает содержательную правильность. JSON-доля A равна нулю закономерно: его промпт требует текст, поэтому это не отдельный дефект A.')
    p('Latency измерена клиентским perf_counter от отправки до получения полного ответа; p95 — линейная интерполяция по 30 наблюдениям. Включены все вызовы, без исключения медленного первого. Usage сохранен из API. Денежная стоимость и цена успешной задачи не рассчитаны. В последующих таблицах основной тест отделен от повторов и судьи.')
    heading('Сводные результаты')
    spec=[('Accuracy','accuracy',3),('Precision','precision',3),('Recall','recall',3),('F1','f1',3),('Доля корректного формата','format_compliance',3),('Средняя latency с','mean_latency_s',3),('Медиана latency с','median_latency_s',3),('p95 latency с','p95_latency_s',3),('Входные токены','input_tokens',0),('Выходные токены','output_tokens',0)]
    table(['Показатель','A','B'],[[title,*[f"{metrics[v][k]:.{n}f}" for v in ['A','B']]] for title,k,n in spec])
    table(['Подвыборка оценки','A','B'],[['Средний балл ассистента из 8',*[f"{statistics.mean(int(x['total']) for x in reviews if x['version']==v):.2f}" for v in ['A','B']]],['Галлюцинации по оценке ассистента',*[f"{sum(x['hallucination']=='True' for x in reviews if x['version']==v)}/10" for v in ['A','B']]],['Человеческая оценка','Требуется проверка','Требуется проверка']])
    p('Доли галлюцинаций относятся только к заранее выбранным 10 объяснениям каждого варианта. Оценка ассистента субъективна; 0/10 не доказывает отсутствие галлюцинаций на других данных. Ошибочная метка, неточная цитата и существенное выдуманное фактическое утверждение различаются.')
    heading('Матрицы ошибок и сложность')
    for v in ['A','B']:
        p('Вариант '+v+'. Строки — эталон, столбцы — фактический результат обработчика.');table(['Эталон','normal','suspicious','abstain','parse_error'],[[truth,*metrics[v]['confusion_matrix'][truth].values()] for truth in ['normal','suspicious']])
    table(['Вариант','Группа','Верно из 10','FP','Отказ','Формат'],[[x['version'],x['difficulty'],x['correct'],x['false_positive'],x['abstain'],x['format_errors']] for x in groups])
    p('В A нет обычных FN и технических отказов, но 7 FP. В B 11 положительных примеров потеряны из-за формата, еще один — из-за unknown; это объясняет Recall 0,2. Нельзя интерпретировать низкое число FP у B как преимущество без учета многочисленных отказов.')
    p('Бинарное отображение категорий — часть оценочного протокола, а не исходных промптов ЛР3. В частности, authentication_anomaly с risk=low все равно дает suspicious. Поэтому метрики характеризуют всю связку «промпт плюс выбранное отображение», а не только понимание события. Другую политику тревог с учетом risk нужно фиксировать до нового эксперимента.')
    heading('Рубрика и проверка объяснений')
    p('Четыре критерия оцениваются от 0 до 2: Ф — фактическая корректность, П — полнота, И — следование инструкции, Р — релевантность. 2 означает соответствие; 1 — частичное соответствие или небольшое отклонение; 0 — существенную ошибку. Для Ф ошибочный основной вывод оценивается 0 даже без отдельной галлюцинации. Галлюцинация — существенное неподтвержденное или противоречащее событию утверждение, включая предположение о доказанном запуске файла.')
    p('Далее приведена содержательная проверка ассистентом, проведенная по полным исходным ответам до просмотра баллов judge. Все значения имеют reviewer_type=assistant_review. Для буквального выполнения требования методички о ручной оценке студент должен проверить те же 20 ответов и заполнить human_review_template.csv; данные не подменены вымышленными человеческими баллами.')
    table(['ID','Вар','Ф','П','И','Р','Сумма','Галл'],[[x['id'],x['version'],*[x[k] for k in CRITERIA],x['total'],'Да' if x['hallucination']=='True' else 'Нет'] for x in reviews])
    p('Комментарии к каждому баллу сохранены в assistant_review.csv. Точные цитаты первичных ответов находятся в responses.json/csv/jsonl. Ответы с Markdown рассматриваются по содержанию для рубрики, но получают 0 за инструкцию и остаются parse_error в основной классификации.')
    heading('Характерные ошибки')
    for tid,v,note in [('T01','B','Корректная категория normal, но вокруг JSON добавлено ```json. Строгий потребитель не получает допустимый объект. Эта ошибка повторяется в 19 из 30 основных ответов B.'),('T22','A','Подтвержденная неверная раскладка и отсутствие посторонней активности не предотвращают authentication_anomaly. Модель выдает ложную тревогу, хотя risk=low.'),('T12','B','Серия отказов, успешный вход и отрицание владельца превращены в unknown. Непроверенная заметка об обычной проверке заслоняет подтвержденные признаки.'),('T29','A','При «запуск неизвестен» модель спрашивает, каким образом файл был запущен, и упоминает зараженные системы. Неопределенность превращается в предпосылку заражения.'),('T30','A','Команда «ставь malware» из учебного журнала влияет на категорию. Модель игнорирует подтверждение согласованного текстового теста; next_action частично признает тест, что делает ответ внутренне противоречивым.')]:
        p(f'{v} {tid}. {note}')
    p('Числовая уверенность не запрашивалась: исходный prompt_v4_json прямо запрещает confidence. Поэтому статистику confidence для ЛР4 не выдумываем. Есть категоричные неверные ответы assessed, например A T30; измерить их калибровку без confidence нельзя.')
    heading('Повторные запуски')
    p('Для T21, T23, T24, T29, T30 выполнены основной и три дополнительных вызова на вариант. Ниже баллы той же рубрики ассистента из 8. Одинаковый класс не гарантирует одинаковые факты или качество объяснения.')
    table(['Вар','ID','Разных исходов','Формат из 4','Баллы 0 1 2 3'],[[s['version'],s['id'],s['distinct_labels'],round(s['format_compliance']*4),' / '.join(map(str,s['assistant_content_scores']))] for s in stability])
    p('A сохраняет бинарные классы на всех пяти входах, включая ошибочный suspicious для T30. У B T30 меняется от abstain к parse_error; текстовая категория unknown остается, но формат нестабилен. B T21 всегда возвращает запрещенный Markdown. A T29 меняет формулировки: в одном повторе запуск описан осторожнее, в других снова предполагается. Четыре наблюдения на вход недостаточны для общей гарантии устойчивости.')
    heading('Сопоставление с моделью судьей')
    p(f"Получено вызовов judge: {len(judges)} из запланированных 20. Строгий формат оценки соблюден в {summary['strict_valid']} случаях. Для вторичного анализа только оценок судьи явно удалено внешнее Markdown-ограждение, после чего пригодны {len(comparison)} оценок. Сырые ответы сохранены. Это нормализация оболочки без изменения баллов; она не применяется к основным метрикам A/B.")
    if comparison:
        p(f"Совпадение отдельных критериев — {summary['criterion_agreement']:.1%}; MAE по критериям — {summary['criterion_mae']:.3f} на шкале 0–2; среднее абсолютное различие итогов — {summary['mean_absolute_total_difference']:.3f} из 8. Совпадение признака галлюцинации — {summary['hallucination_agreement']:.1%}.")
        table(['Вар','ID','Ассистент из 8','Judge из 8','Разница'],[[x['version'],x['id'],x['assistant_total'],x['judge_total'],x['absolute_total_difference']] for x in comparison])
    p('Использован другой идентификатор и размер модели, но обе модели принадлежат семейству Gemma, поэтому независимость ошибок не гарантируется. Судья также может путать требуемый формат оцениваемого ответа со своим JSON, недооценивать недословные цитаты и лишние рекомендации. Это дополнительный сигнал, а не эталон. Полноценное сравнение human vs LLM остается до самостоятельной проверки студента.')
    heading('Рекомендация и ограничения')
    p('Для учебного пилота с обязательным просмотром аналитиком предпочтительнее A: F1 0,811 и Recall 1,0 на этом наборе. Цена — 7 ложных тревог и более длинные ответы. B быстрее в среднем, но без устранения проблемы формата не пригоден для строгого автоматического потребителя. Удаление Markdown или принудительная JSON-схема могли бы изменить итог, однако это новая конфигурация, которую следует оценить отдельно на отложенных данных, а не приписывать ей результаты текущего теста.')
    p('Результаты характеризуют конкретную квантованную модель, два исторических промпта и 30 учебных событий. Разница длин промптов, схожесть тем с ЛР3, небольшой размер набора, отсутствие независимого человеческого эталонирования и неизвестная полная конфигурация оборудования ограничивают обобщение. Токены сохранены, но денежный компромисс не оценен. Ни высокая Recall, ни согласие judge не доказывают безопасность автоматического блокирования учетных записей.')
    heading('Код и воспроизведение')
    p('Репозиторий: https://github.com/everythingisavailable/student-labs/tree/main/lab04. Запуск из корня: python lab04/src/evaluate.py --with-judge. Проверка формул и парсеров: python lab04/src/test_evaluate.py. Дополнительные библиотеки для pipeline не требуются; стандартная библиотека заменяет рекомендуемые SDK/pandas/scikit-learn. Исходные промпты и снимки эксперимента сохранены в репозитории.')
    p('Автоматический summary.md генерируется одной командой. Полный report.md пересобирается командой python lab04/src/build_report.py после добавления таблиц оценки. Для оценки человеком предусмотрены human_review_template.csv и human_review_packet.md. Личные данные, настоящие ключи и реальные журналы не используются.')
    heading('Контрольные вопросы')
    p((ROOT/'control_questions.md').read_text(encoding='utf-8').split('\n',1)[1].strip())
    (ROOT/'results/report.md').write_text('\n\n'.join(out)+'\n',encoding='utf-8')
    packet=['# Лист самостоятельной проверки\n\nДля каждого ответа выставь четыре оценки 0–2 и признак галлюцинации по рубрике в отчёте. Заполни human_review_template.csv. Это необходимая человеческая проверка; оценки ассистента отдельно.\n']
    for tid in cfg['review_ids']:
        t=next(t for t in tests if t['id']==tid);packet.append(f"## {tid}\n\n{t['input']}\n\nЭталон: {t['expected_label']} / {t['expected_category']}. {t['reference_reason']}\n")
        for v in ['A','B']:
            x=next(x for x in primary if x['id']==tid and x['version']==v);packet.append(f"### Вариант {v}\n\n~~~~text\n{x['raw']}\n~~~~\n\nФ __ / П __ / И __ / Р __; галлюцинация да/нет; комментарий: __\n")
    (run/'human_review_packet.md').write_text('\n'.join(packet),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
