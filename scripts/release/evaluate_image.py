"""Evaluate the built candidate itself, not a host source checkout."""
import argparse,json,os
from pathlib import Path
from dotenv import dotenv_values
from scripts.release.docker_cli import run
from scripts.release.container_stack import stack

def main():
    p=argparse.ArgumentParser();p.add_argument('--image',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,default=2);p.add_argument('--limit',type=int);a=p.parse_args()
    if not os.environ.get('OLLAMA_API_KEY'):
        key=dotenv_values('.env').get('OLLAMA_API_KEY')
        if key:os.environ['OLLAMA_API_KEY']=key
    if not os.environ.get('OLLAMA_API_KEY'):p.error('OLLAMA_API_KEY is required')
    a.output.mkdir(parents=True,exist_ok=True)
    image_id=run('image','inspect',a.image,'--format','{{.Id}}').stdout.strip()
    with stack(a.image,cloud=True) as (container,_):
        command=['exec',container,'python','-m','scripts.evaluation.run_suite','--workers',str(a.workers),'--output','/app/storage/evaluation']
        if a.limit:command+=['--limit',str(a.limit)]
        result=run(*command,check=False)
        (a.output/'execution.log').write_text(result.stdout+'\n'+result.stderr)
        for name in ['cases.jsonl','summary.json','configuration.json']:
            payload=run('exec',container,'cat','/app/storage/evaluation/'+name,check=False)
            if payload.returncode==0:(a.output/name).write_text(payload.stdout)
        if not (a.output/'summary.json').is_file():raise RuntimeError('Image evaluation did not produce complete summary; inspect private execution.log')
        summary=json.loads((a.output/'summary.json').read_text())
        summary.update(image_id=image_id,image_reference=a.image,scenario_runner_exit_code=result.returncode,
            execution_environment='candidate Docker image; own Qdrant and synthetic SQL state')
        (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps({'image_id':image_id,'completed':summary['completed'],'scopes':{k:{'cases':v['cases'],'passed':v['passed']} for k,v in summary['scopes'].items()}},indent=2))
        # Quality is enforced by check_gate after judging. A completed scenario
        # failure is retained/scored, not an infrastructure error or a silent pass.
        return int(summary['completed'] != summary['selected_cases'])
if __name__=='__main__':raise SystemExit(main())
