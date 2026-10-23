"""Publish frozen examples and actual per-agent/tool traces with separate metric feedback."""
import argparse,json,uuid,statistics
from pathlib import Path
from datetime import datetime,timezone
from dotenv import dotenv_values
from langsmith import Client
from app.config import PROJECT_ROOT
from scripts.evaluation.judge_answers import clean

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--project',required=True);a=p.parse_args()
    values=dotenv_values(PROJECT_ROOT/'.env')
    import os
    key=os.getenv('LANGSMITH_API_KEY') or values.get('LANGSMITH_API_KEY')
    endpoint=os.getenv('LANGSMITH_ENDPOINT') or values.get('LANGSMITH_ENDPOINT','https://eu.api.smith.langchain.com')
    if not key:p.error('LANGSMITH_API_KEY is required')
    client=Client(api_key=key,api_url=endpoint)
    folder=PROJECT_ROOT/'evaluation/datasets';manifest=json.loads((folder/'market-agents-v1.manifest.json').read_text())
    cases=[json.loads(l) for l in (folder/'market-agents-v1.jsonl').read_text().splitlines()]
    name='market-agents-v1-'+manifest['dataset_sha256'][:12]
    examples=[{'id':str(uuid.uuid5(uuid.NAMESPACE_URL,name+'/'+c['case_id'])),'inputs':{'case_id':c['case_id'],'scope':c['scope'],'query':c.get('query'),'turns':c.get('turns')},'outputs':clean(c),'metadata':{'dataset_sha256':manifest['dataset_sha256']}} for c in cases]
    if not client.has_dataset(dataset_name=name):
        dataset=client.create_dataset(dataset_name=name,description='Frozen synthetic catalog/agent regression references,100 cases. Not human-adjudicated customer traffic.')
    else:dataset=client.read_dataset(dataset_name=name)
    existing={str(example.id) for example in client.list_examples(dataset_id=dataset.id)}
    missing=[example for example in examples if example['id'] not in existing]
    if missing:client.create_examples(dataset_id=dataset.id,examples=missing)
    assert {str(example.id) for example in client.list_examples(dataset_id=dataset.id)}=={example['id'] for example in examples},'Dataset upload coverage mismatch'
    if client.has_project(project_name=a.project):raise RuntimeError('Use a new experiment/project name; do not overwrite prior traces')
    project=client.create_project(project_name=a.project,reference_dataset_id=dataset.id,
        description='Actual agent/tool outputs; imported legacy timings are replay-labelled, never claimed as new model execution.',
        metadata={'dataset_sha256':manifest['dataset_sha256']})
    rows=[json.loads(l) for l in (a.input/'cases.jsonl').read_text().splitlines()]
    judgments=[json.loads(l) for l in (a.input/'judge/judgments.jsonl').read_text().splitlines()]
    for row in rows:
        run_id=uuid.uuid4();now=datetime.now(timezone.utc)
        actual_times='started_at' in row and 'ended_at' in row
        start=datetime.fromisoformat(row['started_at']) if actual_times else now
        end=datetime.fromisoformat(row['ended_at']) if actual_times else now
        metadata={'scope':row['scope'],'measured_seconds':row['duration_seconds'],'historical_export':not actual_times,'workflow_passed':row['passed']}
        client.create_run(name=row['case_id'],id=run_id,run_type='chain',project_name=a.project,
            inputs={'case_id':row['case_id']},outputs=clean({'output':row.get('output'),'checks':row.get('checks'),'error_type':row.get('error_type')}),
            start_time=start,end_time=end,reference_example_id=str(uuid.uuid5(uuid.NAMESPACE_URL,name+'/'+row['case_id'])),extra={'metadata':metadata},tags=[row['scope'],'recorded-results'])
        for i,call in enumerate(row.get('calls',[])):
            timed='started_at' in call and 'ended_at' in call
            client.create_run(name=call.get('component','tool')+'.'+call['operation'],id=uuid.uuid4(),parent_run_id=run_id,run_type='llm' if call['operation']=='chat' else 'tool',project_name=a.project,
                inputs=clean(call.get('input',{})),outputs=clean({'result':call.get('output'),'status':call.get('status'),'usage':call.get('usage')}),
                start_time=datetime.fromisoformat(call['started_at']) if timed else now,
                end_time=datetime.fromisoformat(call['ended_at']) if timed else now,
                extra={'metadata':{'measured_seconds':call['duration_seconds'],'historical_export':not timed,'sequence':i}})
        client.flush()
        client.create_feedback(run_id,'workflow_pass',session_id=project.id,score=int(row['passed']))
        client.create_feedback(run_id,'measured_seconds',session_id=project.id,score=row['duration_seconds'])
        for metric,value in row.get('ranking',{}).items():client.create_feedback(run_id,'retrieval_'+metric,session_id=project.id,score=value)
        for metric in ['correctness','completeness','relevance','faithfulness']:
            values=[j['scores'][metric] for j in judgments if j['valid'] and metric in j['scores'] and (j['id']==row['case_id'] or j['id'].startswith(row['case_id']+'.turn'))]
            if values:client.create_feedback(run_id,metric,session_id=project.id,score=statistics.mean(values),comment=f'Mean across{len(values)} scored answer(s); inspect raw rubric results separately.')
    client.flush()
    result={'dataset':name,'project':a.project,'project_id':str(project.id),'cases_uploaded':len(rows),'endpoint':endpoint}
    (a.input/'langsmith.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
