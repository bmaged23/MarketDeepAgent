"""Require exact coverage, separate agent quality and zero observed critical failures."""
import argparse,json,math
from pathlib import Path
from app.config import PROJECT_ROOT

def assess(summary,rows,judge,policy,baseline):
    errors=[]
    def require(condition,message):
        if not condition:errors.append(message)
    require(summary.get('dataset_sha256')==policy['dataset_sha256'],'Dataset fingerprint mismatch')
    require(summary.get('dataset_version')==policy['dataset_version'],'Dataset version mismatch')
    require(summary.get('completed')==policy['cases'] and len(rows)==policy['cases'],'Not all100 cases completed')
    require(len({r['case_id'] for r in rows})==len(rows),'Duplicate case IDs')
    require(bool(summary.get('image_id')),'Missing candidate image identity')
    for scope,n in policy['counts'].items():
        selected=[r for r in rows if r['scope']==scope]
        require(len(selected)==n,f'{scope}: incomplete case coverage')
        require(all(bool(r.get('checks')) and not r.get('error_type') for r in selected),f'{scope}: missing checks or execution errors')
        value=summary.get('scopes',{}).get(scope,{}).get('pass_rate')
        valid=type(value) in {float,int} and math.isfinite(value) and 0<=value<=1
        require(valid,f'{scope}: invalid score')
        if valid:
            require(abs(value-sum(r['passed'] for r in selected)/n)<1e-8,f'{scope}: inconsistent score')
            require(value>=policy['minimum_scope_pass_rates'][scope],f'{scope}: below absolute quality floor')
            reference=baseline['scopes'][scope]['pass_rate']
            require(value+1e-9>=reference-policy['maximum_absolute_scope_regression'],f'{scope}: regressed beyond limit')
        if scope=='journey':
            for row in selected:
                for key in policy['critical_journey_checks']:
                    require(row.get('checks',{}).get(key) is True,f'{row["case_id"]}: critical {key} missing/failed')
    for row in rows:
        for key,value in row.get('checks',{}).items():
            if key.rsplit('.',1)[-1] in policy['critical_no_false_checks']:
                require(value is True,f'{row["case_id"]}: critical {key} failed')
    expected=policy['expected_answer_judgments']
    require(judge.get('expected_answers')==expected,'Answer coverage is incomplete')
    require(judge.get('completed_judgments')==expected*2 and judge.get('valid_judgments')==expected*2,'Judge coverage is incomplete')
    for metric,floor in policy['minimum_answer_scores'].items():
        data=judge.get('metrics',{}).get(metric,{})
        value=data.get('mean');valid=type(value) in {float,int} and math.isfinite(value) and 0<=value<=1
        require(data.get('scored_answers')==expected and valid,f'{metric}: incomplete/invalid scoring')
        if valid:require(value>=floor,f'{metric}: below quality floor')
    return errors

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);a=p.parse_args()
    policy=json.loads((PROJECT_ROOT/'evaluation/release-policy.json').read_text())
    baseline=json.loads((PROJECT_ROOT/policy['baseline']).read_text())
    summary=json.loads((a.candidate/'summary.json').read_text())
    rows=[json.loads(l) for l in (a.candidate/'cases.jsonl').read_text().splitlines()]
    judge=json.loads((a.candidate/'judge/summary.json').read_text())
    errors=assess(summary,rows,judge,policy,baseline)
    report={'passed':not errors,'errors':errors,'dataset_sha256':policy['dataset_sha256'],'image_id':summary.get('image_id')}
    (a.candidate/'gate.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    return int(bool(errors))
if __name__=='__main__':raise SystemExit(main())
