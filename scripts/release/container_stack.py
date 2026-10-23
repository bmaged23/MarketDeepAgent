"""Disposable image stack; never use the existing user's Qdrant volume for release tests."""
from contextlib import contextmanager
import time,uuid
from scripts.release.docker_cli import run

QDRANT='qdrant/qdrant@sha256:b7b0444c4c351c970b98e90a6f89c2ee4287c65b44e52b4cb503fa5b2aa927ad'

@contextmanager
def stack(image,*,cloud=False):
    name='market-check-'+uuid.uuid4().hex[:10]
    network=name+'-net';database=name+'-db';vectors=name+'-vectors';storage=name+'-data';container=name+'-app'
    run('network','create',network)
    try:
        run('volume','create',vectors);run('volume','create',storage)
        run('run','-d','--name',database,'--network',network,'--mount',f'type=volume,src={vectors},dst=/qdrant/storage',QDRANT)
        common=['--name',container,'--network',network,'--mount',f'type=volume,src={storage},dst=/app/storage',
                '-e','QDRANT_URL=http://'+database+':6333','-e','EMBEDDING_DEVICE=cpu',
                '-e','QDRANT_COLLECTION=market_release_products','-e','OLLAMA_MODEL=gpt-oss:120b',
                '-e','OLLAMA_BASE_URL=https://ollama.com']
        if cloud:common+=['-e','OLLAMA_API_KEY']
        run('run','-d',*common,image)
        for _ in range(180):
            result=run('exec',container,'python','-c',"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8600/healthz',timeout=3)",check=False)
            if result.returncode==0:break
            if run('inspect','--format','{{.State.Running}}',container).stdout.strip()!='true':
                raise RuntimeError('Candidate failed to start: '+run('logs',container).stdout[-1500:])
            time.sleep(2)
        else:raise TimeoutError('Candidate startup did not become live')
        yield container,common
    finally:
        run('rm','-f',container,check=False);run('rm','-f',database,check=False)
        run('volume','rm',storage,vectors,check=False);run('network','rm',network,check=False)
