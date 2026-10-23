"""Run frozen agent scenarios against real catalog/tools; save intermediate traces locally."""
import argparse,hashlib,json,math,time,statistics
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor,as_completed
from app.config import get_settings,PROJECT_ROOT
from app.database.connection import connection
from app.product_search.schemas import SearchFilters
from app.product_search.evaluation import retrieval_metrics
from app.product_search.service import create_search_service
from app.model_clients.factory import embedding_client,vector_index
from app.utils.agent_evaluation import evaluation_catalog,trace_cart,stock
from app.utils.evaluation_trace import RecordedClient
from app.agents.retrieval.agent import create_runner as retrieval_runner
from app.agents.cart.agent import create_runner as cart_runner
from app.agents.customer.agent import CustomerAgent
from app.agents.customer.tools import CustomerTools
from app.agents.cart.evaluation import evaluate_cases as cart_cases
from app.agents.customer.evaluation import evaluate_cases as customer_cases
from app.assistant.service import AssistantService
from app.assistant.schemas import ChatRequest
from app.cart.service import CartService
from app.conversations.service import ConversationService
from app.customer_memory.service import MemoryService
from app.agents.customer.journey_evaluation import NoMemoryVectors
from app.utils.errors import ServiceError
from scripts.performance.benchmark_embeddings import Resources

ROOT=PROJECT_ROOT
RETRIEVAL_METHODS={'categories','resolve_named_products','search_products','query_products','product_details','compare_products'}

def trace_retrieval(runner,records):
    runner.tools=RecordedClient(runner.tools,records,RETRIEVAL_METHODS,'retrieval')
    runner.llm=RecordedClient(runner.llm,records,{'chat'},'retrieval')
    runner.judge.llm=runner.llm
    runner.judge=RecordedClient(runner.judge,records,{'grade'},'retrieval')
    return runner

def chunks(result):
    return [c for section in result.get('sections',[]) for c in section.get('chunks',[])]

def oracle_product_checks(evidence,gold,filters):
    by_id={p['product_id']:p for p in gold}
    facts=True;constraints=True
    for chunk in evidence:
        p=chunk['product'];ref=by_id.get(p['product_id'])
        facts &= ref is not None and all(v==ref.get(k) for k,v in p.items())
        eligibility={**(ref or {}),**p}  # SQL projections may omit filter fields.
        constraints &= (filters.get('category_id') is None or p['category_id']==filters['category_id'])
        constraints &= (filters.get('min_price') is None or eligibility.get('price',-math.inf)>=filters['min_price'])
        constraints &= (filters.get('max_price') is None or eligibility.get('price',math.inf)<=filters['max_price'])
        constraints &= (not filters.get('in_stock') or eligibility.get('stock_quantity',0)>0)
    return {'facts_match_sql':bool(facts),'constraints_satisfied':bool(constraints),
            'approved_only':all(c.get('approval')==1 for c in evidence)}

def retrieval(case,settings,embeddings,vectors):
    records=[]
    search=create_search_service(settings,embeddings,vectors)
    direct=search.search(case['query'],SearchFilters(**case['constraints']),5)
    ranking=retrieval_metrics([r['product']['product_id'] for r in direct['results']],case['relevant_product_ids'],5)
    runner=trace_retrieval(retrieval_runner(settings,search),records)
    try:
        result=runner.run(case['query'])
    except Exception as error:
        return {'passed':False,'calls':records,'checks':{},'error_type':type(error).__name__,'ranking':ranking}
    catalog=json.loads((ROOT/'evaluation/datasets/catalog-v1.json').read_text())['products']
    evidence=chunks(result);found={c['product']['product_id'] for c in evidence}
    checks=oracle_product_checks(evidence,catalog,case['constraints'])
    checks.update(expected_products_found=set(case['relevant_product_ids'])<=found,
                  retrieval_complete=result['retrieval_ok'],no_degraded_search=not result['degraded'] and not direct['degraded'],
                  search_budget=result['searches']<=settings.retrieval_max_searches,
                  no_mutation_tools=all(c['operation'] in RETRIEVAL_METHODS|{'chat','grade'} for c in records))
    # Accept SQL and hybrid alternatives; evaluate returned facts/constraints, not one hard-coded tool sequence.
    sql_calls=[c for c in records if c['operation']=='query_products']
    sql_valid=True
    for call in sql_calls:
        output=call.get('output',{})
        selection=output.get('selection',{})
        if selection.get('all_matches') and selection.get('next_offset') is not None and result['retrieval_ok']:
            # Later pages are valid when actually executed, not merely proposed.
            offsets={c.get('output',{}).get('selection',{}).get('offset') for c in sql_calls}
            sql_valid &= selection['next_offset'] in offsets
    checks['sql_pagination_complete']=bool(sql_valid)
    return {'output':result,'calls':records,'checks':checks,'passed':all(checks.values()),
            'ranking':ranking,'agent_recall':len(found&set(case['relevant_product_ids']))/len(case['relevant_product_ids']),
            'model_usage':getattr(runner.llm,'usage',[])}

def journey(case,settings,embeddings,vectors):
    records=[];turns=[];all_checks={}
    with evaluation_catalog(settings) as (isolated,_,_):
        search=create_search_service(isolated,embeddings,vectors)
        memory=MemoryService(isolated,embeddings,NoMemoryVectors())
        memory.set_enabled(1,False);memory.set_enabled(2,False)
        def factory(current,service,owner):
            retriever=trace_retrieval(retrieval_runner(current,service),records)
            cart=trace_cart(cart_runner(current,owner),records)
            tools=RecordedClient(CustomerTools(retriever,cart),records,{'retrieve_products','manage_cart','complete_confirmed_order'},'customer')
            from app.model_clients.ollama import OllamaClient
            llm=RecordedClient(OllamaClient(current),records,{'chat'},'customer')
            return CustomerAgent(current,tools,llm)
        service=AssistantService(isolated,search,ConversationService(isolated),memory,factory)
        cart=CartService(isolated.database_path)
        before={p['product_id']:stock(isolated,p['product_id']) for p in case['reference_evidence']}
        cid=None;references=[];quote=None
        for i,turn in enumerate(case['turns']):
            start=len(records);t=time.perf_counter()
            try:
                result=service.chat(1,ChatRequest(query=turn['query'],conversation_id=cid,
                    page_context={'page':'shop','referenced_product_ids':references}))
            except Exception as error:
                turns.append({'turn':i+1,'query':turn['query'],'error_type':type(error).__name__,
                    'calls':records[start:],'duration_seconds':time.perf_counter()-t})
                all_checks[f'turn_{i+1}.execution_completed']=False
                return {'passed':False,'output':turns,'calls':records,'checks':all_checks,'error_type':type(error).__name__}
            cid=result['conversation_id']
            references=list(dict.fromkeys([*references,*[p['product_id'] for p in result.get('products',[])]]))
            actual=cart.view(1)
            quantities={str(p['product_id']):p['quantity'] for p in actual['items']}
            checks={'cart_quantities':quantities==turn['expected_cart'],
                'no_unconfirmed_order':not cart.history(1),
                'no_other_customer_mutation':not cart.view(2)['items'] and not cart.history(2),
                'no_early_stock_deduction':all(stock(isolated,k)==v for k,v in before.items()),
                'answer_present':bool(result.get('answer','').strip())}
            if 'expected_products' in turn:
                approved={c['product']['product_id'] for c in chunks(result.get('results',{}).get('retrieval',{}))}
                checks['requested_products_found']=set(turn['expected_products'])<=approved
            if turn.get('expected_quote'):
                quote=result.get('results',{}).get('cart',{}).get('output',{})
                checks['quote_ready']=quote.get('ready') is True and bool(quote.get('confirmation_token'))
                checks['quoted_total']=quote.get('cart',{}).get('total')==case['reference_answer_facts']['expected_total']
            turns.append({'turn':i+1,'query':turn['query'],'output':result,'checks':checks,'calls':records[start:],'duration_seconds':time.perf_counter()-t})
            all_checks.update({f'turn_{i+1}.{k}':v for k,v in checks.items()})
        token=(quote or {}).get('confirmation_token')
        if token:
            body={'token':token,'confirmed':True,'payment_method':'cash_on_delivery','delivery_address':'Synthetic evaluation address'}
            try:cart.checkout(2,body);blocked=False
            except ServiceError as e:blocked=e.status_code==404
            all_checks['cross_customer_checkout_blocked']=blocked
            first=cart.checkout(1,body);repeat=cart.checkout(1,body)
            all_checks.update(idempotent_checkout=repeat['already_completed'],cart_empty_after_checkout=not cart.view(1)['items'],
                one_owned_order=len(cart.history(1))==1,other_orders_isolated=not cart.history(2),
                unpaid_cash_on_delivery=first['order']['payment_status']=='unpaid',
                final_total=first['order']['total_amount']==case['reference_answer_facts']['expected_total'],
                stock_deducted_once=all(stock(isolated,k)==v-case['reference_answer_facts']['expected_final_quantities'][str(k)] for k,v in before.items()))
            try:cart.order(2,first['order']['order_id']);blocked=False
            except ServiceError as e:blocked=e.status_code==404
            all_checks['cross_customer_order_blocked']=blocked
        else:all_checks['confirmed_checkout_possible']=False
        return {'output':turns,'calls':records,'checks':all_checks,'passed':all(all_checks.values())}

def execute(case,settings,embeddings,vectors,resources=None):
    started=time.perf_counter()
    cpu_started=time.process_time()
    rss_start=len(resources.rss) if resources else 0
    gpu_start=len(resources.gpu) if resources else 0
    started_at=datetime.now(timezone.utc).isoformat()
    try:
        if case['scope']=='retrieval':row=retrieval(case,settings,embeddings,vectors)
        elif case['scope']=='cart':row=cart_cases(settings,[case['base_case']],query_override=case['query'])[0]
        elif case['scope']=='customer':row=customer_cases(settings,[case['base_case']],embeddings=embeddings,vectors=vectors,query_override=case['query'])[0]
        else:row=journey(case,settings,embeddings,vectors)
    except Exception as e:row={'passed':False,'error_type':type(e).__name__,'checks':{},'calls':[]}
    row.update(case_id=case['case_id'],scope=case['scope'],duration_seconds=time.perf_counter()-started,
        started_at=started_at,ended_at=datetime.now(timezone.utc).isoformat())
    if resources:
        gpu=resources.gpu[gpu_start:]
        row['resource_observations']={'shared_process_peak_rss_mib':max(resources.rss[rss_start:] or resources.rss[-1:],default=None),
            'shared_process_cpu_percent_one_core_100':100*(time.process_time()-cpu_started)/row['duration_seconds'],
            'whole_device_peak_vram_mib':max((g[0] for g in gpu),default=None),
            'whole_device_peak_gpu_percent':max((g[1] for g in gpu),default=None),
            'scope':'Shared worker during this case; overlapping cases/other GPU users are included, not per-user attribution.'}
    return row

def validate_dataset(root=ROOT):
    folder=root/'evaluation/datasets'
    manifest=json.loads((folder/'market-agents-v1.manifest.json').read_text())
    raw=(folder/'market-agents-v1.jsonl').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==manifest['dataset_sha256'],'Dataset fingerprint mismatch'
    assert hashlib.sha256((folder/'catalog-v1.json').read_bytes()).hexdigest()==manifest['catalog_sha256'],'Catalog fingerprint mismatch'
    cases=[json.loads(line) for line in raw.decode().splitlines()]
    assert len(cases)==100 and len({c['case_id'] for c in cases})==100
    assert {s:sum(c['scope']==s for c in cases) for s in manifest['counts']}==manifest['counts']
    return manifest,cases

def application_fingerprint():
    digest=hashlib.sha256()
    for path in sorted((ROOT/'app').rglob('*')):
        if path.is_file() and path.suffix in {'.py','.md','.sql'}:
            digest.update(path.relative_to(ROOT).as_posix().encode()+b'\0'+path.read_bytes()+b'\0')
    return digest.hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scope',choices=['all','retrieval','cart','customer','journey'],default='all')
    parser.add_argument('--limit',type=int);parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--resume',action='store_true',help='Keep every completed result, including failures; execute only missing case IDs')
    parser.add_argument('--output',type=Path,default=ROOT/'.evaluation-local/live');args=parser.parse_args()
    if args.workers<1 or (args.limit is not None and args.limit<1):parser.error('workers and limit must be positive')
    manifest,cases=validate_dataset();application_sha=application_fingerprint()
    cases=[c for c in cases if args.scope=='all' or c['scope']==args.scope]
    if args.limit:cases=cases[:args.limit]
    args.output.mkdir(parents=True,exist_ok=True)
    settings=get_settings();embeddings=embedding_client(settings);vectors=vector_index(settings)
    resources=Resources(sample_gpu=settings.embedding_device.startswith('cuda'));resources.start()
    resource_wall=time.perf_counter();resource_cpu=time.process_time()
    # Model startup is recorded separately; case times are warm except model-specific cloud startup.
    t=time.perf_counter();embeddings.encode_query('Warm up catalog retrieval');startup=time.perf_counter()-t
    rows=[];started=time.perf_counter()
    case_path=args.output/'cases.jsonl'
    if args.resume and case_path.exists():
        rows=[json.loads(line) for line in case_path.read_text().splitlines()]
        expected={c['case_id']:c['scope'] for c in cases}
        assert len({r['case_id'] for r in rows})==len(rows),'Duplicate completed cases'
        assert all(expected.get(r['case_id'])==r['scope'] for r in rows),'Completed cases do not match selected dataset'
    completed_ids={r['case_id'] for r in rows}
    pending=[c for c in cases if c['case_id'] not in completed_ids]
    configuration={'dataset_sha256':manifest['dataset_sha256'],'application_sha256':application_sha,
        'model':settings.ollama_model,'embedding_revision':settings.embedding_revision,
        'embedding_device':settings.embedding_device,'resume_existing_cases':len(rows)}
    config_path=args.output/'configuration.json'
    if args.resume and config_path.exists():
        previous=json.loads(config_path.read_text())
        for key in ['dataset_sha256','application_sha256','model','embedding_revision','embedding_device']:
            if key in previous:assert previous[key]==configuration[key],f'Cannot resume changed {key}; use a new experiment'
    config_path.write_text(json.dumps(configuration,indent=2)+'\n')
    try:
        with case_path.open('a' if args.resume else 'w') as handle,ThreadPoolExecutor(max_workers=args.workers) as executor:
            jobs={executor.submit(execute,c,settings,embeddings,vectors,resources):c['case_id'] for c in pending}
            for future in as_completed(jobs):
                row=future.result();rows.append(row);handle.write(json.dumps(row,ensure_ascii=False)+'\n');handle.flush()
                print(json.dumps({'case_id':row['case_id'],'passed':row['passed'],'seconds':round(row['duration_seconds'],2),'failed_checks':[k for k,v in row.get('checks',{}).items() if not v],'error_type':row.get('error_type')}),flush=True)
    finally:
        vectors.close();resources.finish()
    summaries={}
    for scope in manifest['counts']:
        subset=[r for r in rows if r['scope']==scope]
        if not subset:continue
        checks={k for r in subset for k in r.get('checks',{})}
        summaries[scope]={'cases':len(subset),'passed':sum(r['passed'] for r in subset),'pass_rate':sum(r['passed'] for r in subset)/len(subset),
            'median_seconds':statistics.median(r['duration_seconds'] for r in subset),'checks':{k:{'passed':sum(r.get('checks',{}).get(k) is True for r in subset),'scored':sum(k in r.get('checks',{}) for r in subset)} for k in sorted(checks)}}
        if scope=='retrieval':
            scored=[r for r in subset if 'ranking' in r]
            summaries[scope]['ranking']={k:statistics.mean(r['ranking'][k] for r in scored) for k in scored[0]['ranking']} if scored else {}
            summaries[scope]['ranking_scored']=len(scored)
    summary={'dataset_version':manifest['version'],'dataset_sha256':manifest['dataset_sha256'],'application_sha256':application_sha,'selected_cases':len(cases),'completed':len(rows),'mode':'live_ollama_real_tools',
        'model':settings.ollama_model,'embedding_device':settings.embedding_device,'model_load_seconds':startup,'wall_seconds':time.perf_counter()-started,'resumed_cases':len(completed_ids),'wall_time_scope':'This invocation only; per-case durations retain prior attempts.','workers':args.workers,'scopes':summaries,
        'resource_usage':{'peak_worker_rss_mib':max(resources.rss,default=None),
            'mean_worker_cpu_percent_one_core_100':100*(time.process_time()-resource_cpu)/(time.perf_counter()-resource_wall),
            'whole_device_peak_vram_mib':max((g[0] for g in resources.gpu),default=None),
            'whole_device_peak_gpu_utilization_percent':max((g[1] for g in resources.gpu),default=None),
            'scope':'Evaluation worker incl. model startup; excludes Qdrant, browser and cloud servers. GPU observations include other device users.'},
        'limitations':['Synthetic regression cases, not independent human-adjudicated shoppers.','Ranked retrieval and SQL/agent evidence are scored separately.','Parallel case times overlap; shared process/GPU resource use is not attributable to one user.','No live customer database or memory is modified; journeys use isolated synthetic SQL.']}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    return int(any(not r['passed'] for r in rows))
if __name__=='__main__':raise SystemExit(main())
