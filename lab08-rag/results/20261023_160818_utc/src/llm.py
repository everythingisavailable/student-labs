import os,json,time,urllib.request
from urllib.parse import urlparse
from common import ROOT,readjson

def api_request(path,body=None):
    cfg=readjson(ROOT/'config.json');base=os.getenv('LOCAL_BASE_URL',cfg['base_url']).rstrip('/')
    if urlparse(base).hostname not in ['localhost','127.0.0.1','::1']:raise ValueError('Only loopback LLM endpoints allowed')
    headers={'Content-Type':'application/json'}
    if os.getenv('LOCAL_API_KEY'):headers['Authorization']='Bearer '+os.environ['LOCAL_API_KEY']
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    # No proxy and no redirects to external destinations.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    with opener.open(req,timeout=cfg['timeout_s']) as response:return json.load(response)

def llm_chat(messages):
    cfg=readjson(ROOT/'config.json');body=dict(model=cfg['llm_model'],messages=messages,temperature=cfg['temperature'],max_tokens=cfg['max_tokens'],seed=cfg['llm_seed'],stream=False)
    start=time.perf_counter()
    try:
        data=api_request('/api/v0/chat/completions',body);choice=data['choices'][0]
        result=dict(answer=choice['message'].get('content') or '',finish_reason=choice.get('finish_reason'),api_response=data,error=None)
    except Exception as exc:result=dict(answer='',finish_reason=None,api_response=None,error=type(exc).__name__)
    result['llm_latency_s']=time.perf_counter()-start
    return result
