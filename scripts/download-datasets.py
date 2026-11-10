"""Download verified originals. Never overwrite an existing mismatched source."""
from pathlib import Path
import hashlib,sys,urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.catalog import DEPLOYMENTS,PUBLICATION

for d in DEPLOYMENTS.values():
    target=d['path'];target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if hashlib.md5(target.read_bytes()).hexdigest()!=d['md5']:raise SystemExit('Existing source checksum differs: '+target.name)
        print('Verified existing:',target.name);continue
    temporary=target.with_suffix('.xlsx.part')
    request=urllib.request.Request(PUBLICATION+'/files/'+d['filename']+'?download=1',headers={'User-Agent':'Verdant-Course-Platform/1.0'})
    with urllib.request.urlopen(request,timeout=240) as response,temporary.open('wb') as output:
        while chunk:=response.read(1024*1024):output.write(chunk)
    if hashlib.md5(temporary.read_bytes()).hexdigest()!=d['md5']:raise SystemExit('Download checksum differs; original not installed: '+target.name)
    temporary.replace(target);print('Downloaded and verified:',target.name)
