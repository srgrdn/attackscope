"""Verify an explicitly started local test TLS proxy with synthetic demo replay."""

import argparse
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--ca", type=Path, required=True)
args = parser.parse_args()
certificate = args.ca.read_text()
script = """
import json,ssl
from pathlib import Path
from datetime import datetime,timedelta
from urllib.request import Request,build_opener,HTTPSHandler,ProxyHandler
from urllib.error import HTTPError
context=ssl.create_default_context(cadata=CERTIFICATE)
opener=build_opener(ProxyHandler({}),HTTPSHandler(context=context))
manifest=json.loads(Path('/data/demo/morning/manifest.json').read_text())
token=Path('/data/demo/morning/http.token').read_text().strip()
item=json.loads(Path('/app/fixtures/investigation.json').read_text())[0]
payload={**item['payload'],'timestamp':(datetime.fromisoformat(manifest['base_time'])+timedelta(seconds=item['offset_seconds'])).isoformat()}
body=json.dumps([{'transport_version':1,'source':'http','source_reference':item['source_reference'],'payload':payload}]).encode()
request=Request('https://tls-ingress:8443/api/v1/ingest/events',data=body,headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
with opener.open(request,timeout=15) as response:
    result=json.load(response)
    assert result['accepted']==0 and result['duplicates']==1
print('TLS certificate/hostname verified; authenticated replay deduplicated')
try:
    opener.open(Request('https://tls-ingress:8443/api/v1/ingest/events',data=body,headers={'Content-Type':'application/json'}),timeout=15)
except HTTPError as error:
    assert error.code==401
    print('TLS unauthorized source rejected: 401')
else:
    raise AssertionError('Unauthenticated ingestion accepted')
""".replace("CERTIFICATE", repr(certificate))
subprocess.run(
    ["docker", "compose", "exec", "-T", "backend", "python", "-"],
    input=script,
    text=True,
    check=True,
)
