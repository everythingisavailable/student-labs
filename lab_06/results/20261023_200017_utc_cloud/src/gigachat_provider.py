"""GigaChat OAuth and TLS verification. Tokens exist only in process memory."""
import json,ssl,time,uuid,urllib.request,urllib.parse
from pathlib import Path

_token=None
_expires_at=0

def _call(url,headers,body=None,cfg=None):
    context=ssl.create_default_context()
    ca=(cfg or {}).get('GIGACHAT_CA_BUNDLE')
    if ca:context.load_verify_locations(cafile=str(Path(ca)))
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=urllib.request.build_opener(urllib.request.HTTPSHandler(context=context),NoRedirect())
    req=urllib.request.Request(url,data=body,headers=headers)
    with opener.open(req,timeout=180) as r:return json.load(r)

def token(cfg):
    global _token,_expires_at
    if _token and time.time()<_expires_at-60:return _token
    credential=cfg.get('GIGACHAT_AUTH_KEY')
    if not credential:raise ValueError('GigaChat authorization key missing')
    scope=cfg.get('GIGACHAT_SCOPE','GIGACHAT_API_PERS')
    if scope!='GIGACHAT_API_PERS':raise ValueError('This experiment is configured for personal Freemium access')
    data=_call('https://ngw.devices.sberbank.ru:9443/api/v2/oauth',
        {'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json',
         'RqUID':str(uuid.uuid4()),'Authorization':'Basic '+credential},
        urllib.parse.urlencode({'scope':scope}).encode(),cfg)
    _token=data['access_token'];_expires_at=data['expires_at']/1000
    return _token

def call(cfg,path,body=None):
    if cfg.get('CLOUD_BASE_URL')!='https://api.giga.chat/v1':raise ValueError('Unexpected GigaChat base URL')
    return _call('https://api.giga.chat/v1'+path,
        {'Content-Type':'application/json','Accept':'application/json','Authorization':'Bearer '+token(cfg)},
        json.dumps(body,ensure_ascii=False).encode('utf-8') if body is not None else None,cfg)
