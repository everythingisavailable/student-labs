"""Use the official public CA in this client only; system trust is unchanged."""
from pathlib import Path
import hashlib,ssl,urllib.request
ROOT=Path(__file__).resolve().parents[1]
URL='https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt'
PIN='936a43fea6e8e525bcc0f81acd9c3d21b4fc4b9b68acea7906d698005afc6504'
def main():
    with urllib.request.urlopen(URL,timeout=30,context=ssl.create_default_context()) as r:data=r.read()
    if hashlib.sha256(data).hexdigest()!=PIN:raise SystemExit('Certificate changed; review the official certificate before updating the pin.')
    folder=ROOT/'certs';folder.mkdir(exist_ok=True);path=folder/'russian_trusted_root_ca_pem.crt';path.write_bytes(data)
    ssl.create_default_context().load_verify_locations(cafile=str(path))
    print('CA saved. Set GIGACHAT_CA_BUNDLE=certs/russian_trusted_root_ca_pem.crt in .env')
if __name__=='__main__':main()
