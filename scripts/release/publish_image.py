"""Publish only the exact image identity referenced by the successful quality gate."""
import argparse,json
from pathlib import Path
from scripts.release.docker_cli import run

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',required=True);p.add_argument('--evaluation',type=Path,required=True)
    p.add_argument('--repository',required=True);p.add_argument('--commit',required=True);a=p.parse_args()
    gate=json.loads((a.evaluation/'gate.json').read_text())
    current=run('image','inspect',a.candidate,'--format','{{.Id}}').stdout.strip()
    if gate.get('passed') is not True or gate.get('image_id')!=current:raise RuntimeError('Candidate identity does not match successful quality gate')
    tags=[a.repository+':cpu',a.repository+':latest',a.repository+':sha-'+a.commit]
    for tag in tags:
        run('tag',a.candidate,tag);run('push',tag,capture=False)
    digests=json.loads(run('image','inspect',tags[-1],'--format','{{json .RepoDigests}}').stdout)
    result={'image_id':current,'tags':tags,'repository_digests':digests,'source_commit':a.commit}
    (a.evaluation/'publication.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
