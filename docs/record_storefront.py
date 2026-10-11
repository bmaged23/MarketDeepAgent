"""Record the real storefront against isolated SQL and real Ollama/Qdrant.

npm --prefix docs install
npm --prefix docs run install-browser
python docs/record_storefront.py
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import get_settings
from app.database.connection import connection
from app.utils.agent_evaluation import evaluation_catalog


class DisabledMemoryVectors:
    """Demo users cannot write to the shared customer memory collection."""
    def close(self):
        pass
    def __getattr__(self, name):
        raise RuntimeError('Shared memory vectors are disabled for this recording')


def serve(port):
    import uvicorn
    from app.main import create_app
    uvicorn.run(create_app(memory_vectors=DisabledMemoryVectors()), host='127.0.0.1', port=port, log_level='warning')


def convert(raw, cuts, destination):
    """Only trim long waiting periods; preserve the actual captured application."""
    probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(raw)],text=True))
    duration=float(probe['format']['duration']);start=0.0;segments=[]
    for cut in cuts:
        a,b=max(start,float(cut['start'])),min(duration,float(cut['end']))
        if b<=a:continue
        if a>start:segments.append((start,a))
        start=b
    if start<duration:segments.append((start,duration))
    filters=[]
    for i,(a,b) in enumerate(segments):filters.append(f'[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{i}]')
    filters.append(''.join(f'[v{i}]' for i in range(len(segments)))+f'concat=n={len(segments)}:v=1:a=0[out]')
    temporary=destination.with_name('storefront-tour.converting.mp4')
    try:
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(raw),'-filter_complex',';'.join(filters),'-map','[out]','-an','-c:v','libx264','-preset','medium','-crf','20','-r','30','-pix_fmt','yuv420p','-movflags','+faststart',str(temporary)],check=True)
        subprocess.run(['ffmpeg','-v','error','-i',str(temporary),'-f','null','-'],check=True)
        temporary.replace(destination)
    finally:temporary.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8601)
    parser.add_argument('--headed',action='store_true',help='Watch the real browser perform the walkthrough')
    parser.add_argument('--serve',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.serve:serve(args.port);return
    if not 1024<=args.port<=65535:parser.error('Choose a port between 1024 and 65535')
    if not shutil.which('node') or not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        parser.error('Node.js and FFmpeg/ffprobe must be installed')
    if not (ROOT/'docs/node_modules/playwright').is_dir():
        parser.error('Install the browser recorder first: npm --prefix docs install; npm --prefix docs run install-browser')
    preflight=['node',str(ROOT/'docs/record_storefront.mjs'),'--check-browser']
    if args.headed:preflight.append('--headed')
    if subprocess.run(preflight,cwd=ROOT).returncode:
        parser.error('Browser preflight failed. Install Chromium using the commands above, then rerun. The demo backend was not started.')
    settings=get_settings()
    if not settings.ollama_api_key.get_secret_value():parser.error('Set OLLAMA_API_KEY in .env')
    base=f'http://127.0.0.1:{args.port}'
    try:
        urllib.request.urlopen(base+'/api/categories',timeout=2).close()
    except (urllib.error.URLError,TimeoutError):pass
    else:parser.error(f'Port {args.port} is already in use; select another --port')
    # Real customer/order/stock data is never cloned or mutated.
    with evaluation_catalog(settings) as (isolated,rows,_), tempfile.TemporaryDirectory(prefix='market-browser-tour-') as directory:
        required={'Apples 1kg','Lipton Yellow Label Tea','Whole Wheat Bread','Greek Yogurt','Mixed Nuts 500g'}
        if not required <= {p['name'] for p in rows if p['stock_quantity']>=2}:parser.error('Tour needs apples, yellow label tea, whole wheat bread, Greek yogurt and mixed nuts with stock >=2')
        with connection(isolated.database_path,write=True) as db:
            db.execute('CREATE TRIGGER demo_memory_disabled AFTER INSERT ON person BEGIN INSERT INTO customer_preferences(person_id,memory_enabled) VALUES(NEW.person_id,0); END;')
        env=os.environ.copy();env['DATABASE_PATH']=str(isolated.database_path)
        log=Path(directory)/'server.log'
        with log.open('w') as handle:
            server=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--serve','--port',str(args.port)],cwd=ROOT,env=env,stdout=handle,stderr=subprocess.STDOUT)
            try:
                for _ in range(100):
                    if server.poll() is not None:raise RuntimeError('Demo backend failed to start; check dependency setup')
                    try:
                        urllib.request.urlopen(base+'/api/categories',timeout=2).close();break
                    except (urllib.error.URLError,TimeoutError):time.sleep(.3)
                else:raise RuntimeError('Demo backend did not become ready')
                capture=ROOT/'docs/assets/raw-recordings';capture.mkdir(parents=True,exist_ok=True)
                manifest=capture/'last-run.json'
                command=['node',str(ROOT/'docs/record_storefront.mjs'),'--url',base,'--output',str(capture),'--manifest',str(manifest)]
                if args.headed:command.append('--headed')
                if subprocess.run(command,cwd=ROOT).returncode:
                    raise SystemExit('Browser walkthrough failed; no replacement video was published. Check the browser output above.')
                run=json.loads(manifest.read_text());output=ROOT/'docs/assets/storefront-tour.mp4'
                convert(Path(run['video']),run['waiting_cuts'],output)
                subprocess.run(['ffmpeg','-v','error','-i',str(output),'-frames:v','1','-y',str(ROOT/'docs/assets/storefront-poster.png')],check=True)
                print(f'Recorded real application walkthrough: {output}')
                print('Real frontend, real live agent replies, one synthetic order. Long waiting periods trimmed. Production SQL and user memory untouched.')
            finally:
                server.terminate()
                try:server.wait(timeout=10)
                except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':main()
