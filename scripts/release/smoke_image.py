"""Test actual container API/model and persistence across replacement containers."""
import argparse,json
from pathlib import Path
from scripts.release.container_stack import stack
from scripts.release.docker_cli import run

def main():
    p=argparse.ArgumentParser();p.add_argument('--image',required=True);a=p.parse_args()
    with stack(a.image) as (container,common):
        source=Path(__file__).with_name('smoke_inside.py').read_text()
        result=run('exec','-i',container,'python','-',input=source)
        report=json.loads(result.stdout.strip().splitlines()[-1]);profile=report.pop('synthetic_profile')
        run('rm','-f',container)
        # Same image, same owned named volume, separate container and process.
        run('run','-d',*common,a.image)
        code='''import httpx,time,json,sys
profile=json.loads(sys.stdin.read())
for _ in range(120):
 try:
  c=httpx.Client(base_url='http://127.0.0.1:8600',timeout=10)
  r=c.post('/api/login',json={'email':profile['email'],'password':profile['password']})
  if r.status_code==200:
   assert c.get('/api/me').json()['email']==profile['email']
   assert not c.get('/api/cart').json()['items']
   print('Stored account and cart survived container replacement');break
 except httpx.RequestError:pass
 time.sleep(1)
else:raise RuntimeError('Persistence check failed')
'''
        run('exec','-i',container,'python','-c',code,input=json.dumps(profile))
        report['checks'].append('account and cart persistence across container replacement')
        print(json.dumps(report,indent=2))
if __name__=='__main__':main()
