"""Bounded local HTTP transport; never follow redirects or proxy local data."""
import json,os,time,urllib.request
from urllib.parse import urlparse

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class LocalAPI:
    def __init__(self,model=None,temperature=.2,max_tokens=650,seed=42):
        self.base=os.getenv('LLM_BASE_URL','http://127.0.0.1:1234/v1').rstrip('/')
        if urlparse(self.base).hostname not in ('localhost','127.0.0.1','::1'):raise ValueError('loopback_only')
        self.model=model or os.getenv('LLM_MODEL','gemma-4-12b-coder-fable5-composer2.5-v1')
        self.temperature=temperature;self.max_tokens=max_tokens;self.seed=seed
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        self.records=[]
    def chat(self,messages,tools=None,timeout=90):
        body={'model':self.model,'messages':messages,'temperature':self.temperature,'max_tokens':self.max_tokens,'seed':self.seed,'stream':False,'reasoning_effort':'none'}
        if tools is not None:body.update(tools=tools,tool_choice='auto')
        headers={'Content-Type':'application/json'}
        if os.getenv('LLM_API_KEY'):headers['Authorization']='Bearer '+os.environ['LLM_API_KEY']
        req=urllib.request.Request(self.base+'/chat/completions',data=json.dumps(body,ensure_ascii=False).encode(),headers=headers)
        t=time.perf_counter()
        try:
            with self.opener.open(req,timeout=timeout) as f:
                raw=f.read(2_000_001)
                if len(raw)>2_000_000:raise ValueError('response_limit')
                data=json.loads(raw)
            choice=data['choices'][0];msg=choice['message']
            if not isinstance(msg,dict):raise ValueError('invalid_message')
            self.records.append({'request':body,'response':data,'latency_s':time.perf_counter()-t})
            if choice.get('finish_reason')=='length':raise ValueError('generation_truncated')
            return {k:msg[k] for k in ('role','content','tool_calls') if k in msg}
        except Exception as exc:
            self.records.append({'error':type(exc).__name__,'latency_s':time.perf_counter()-t})
            raise
