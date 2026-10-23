import argparse,re,json,time
from retrieve import Retriever
from prompt import SYSTEM_PROMPT,build_context
from llm import llm_chat

def citation_check(answer,count):
    brackets=re.findall(r'\[[^\]\n]*\]',answer)
    groups=[g for g in brackets if re.search(r'\bS\d+',g)]
    used=sorted(set(int(x) for g in groups for x in re.findall(r'\bS(\d+)\b',g)))
    nonstandard=[g for g in groups if not re.fullmatch(r'\[S\d+\]',g)]
    return dict(used=used,invalid=[i for i in used if i<1 or i>count],all_labels_exist=all(1<=i<=count for i in used),has_citations=bool(used),nonstandard_groups=nonstandard)

def rag_answer(question,retriever,k=4,role='students'):
    start=time.perf_counter();results,order=retriever.retrieve(question,k,role);retrieval_s=time.perf_counter()-start
    context=build_context(results);messages=[dict(role='system',content=SYSTEM_PROMPT),dict(role='user',content=f'CONTEXT:\n{context}\n\nQUESTION:\n{question}')]
    answer=llm_chat(messages)
    return dict(question=question,k=k,role=role,retrieved=results,ranking=order,context=context,messages=messages,context_chars=len(context),retrieval_s=retrieval_s,total_s=time.perf_counter()-start,**answer,citations=citation_check(answer['answer'],len(results)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('question');p.add_argument('--k',type=int,default=4);p.add_argument('--role',choices=['students','admins'],default='students');args=p.parse_args()
    print(json.dumps(rag_answer(args.question,Retriever(),args.k,args.role),ensure_ascii=False,indent=2))
