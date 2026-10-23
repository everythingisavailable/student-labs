"""Shared request format; credentials are never written into results."""
from pathlib import Path
import os,json,time,urllib.request
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]
def settings():
 values={}
 p=ROOT/'.env'
 if p.exists():
  for line in p.read_text(encoding='utf-8-sig').splitlines():
   if '=' in line and not line.lstrip().startswith('#'):
    k,v=line.split('=',1);values[k.strip()]=v.strip().strip('\"\'')
 return {**values,**os.environ}
def request(base,path,body=None,key=None):
 headers={'Content-Type':'application/json'}
 if key:headers['Authorization']='Bearer '+key
 req=urllib.request.Request(base.rstrip('/')+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,*args,**kwargs):return None
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
 with opener.open(req,timeout=180) as r:return json.load(r)
def ask(backend,prompt,system):
 cfg=settings();prefix=backend.upper();base=cfg.get(prefix+'_BASE_URL','');model=cfg.get(prefix+'_MODEL','');key=cfg.get(prefix+'_API_KEY')
 if backend=='local':
  if urlparse(base).hostname not in ['localhost','127.0.0.1','::1']:raise ValueError('Local endpoint must be loopback')
 elif backend=='cloud':
  if not key:raise ValueError('Cloud key missing')
  if base!='https://openrouter.ai/api/v1':raise ValueError('Cloud provider needs explicit configuration review')
  if not model.endswith(':free'):raise ValueError('Only a fixed free model is authorized')
 else:raise ValueError('Unknown backend')
 payload=dict(model=model,messages=[dict(role='system',content=system),dict(role='user',content=prompt)],temperature=.2,max_tokens=650,stream=False)
 start=time.perf_counter()
 try:
  data=request(base,'/chat/completions',payload,key);choice=data['choices'][0];result=dict(answer=choice['message'].get('content') or '',finish_reason=choice.get('finish_reason'),api_response=data,error=None)
 except Exception as exc:result=dict(answer='',finish_reason=None,api_response=None,error=type(exc).__name__)
 elapsed=time.perf_counter()-start;usage=(result['api_response'] or {}).get('usage') or {}
 return dict(backend=backend,requested_model=model,messages=payload['messages'],temperature=.2,max_tokens=650,latency_s=elapsed,input_tokens=usage.get('prompt_tokens'),output_tokens=usage.get('completion_tokens'),ttft_s=None,ttft_note='Non-streaming request; not measured',output_tokens_per_total_second=usage['completion_tokens']/elapsed if usage.get('completion_tokens') is not None else None,**result)
