"""Measure this project's actual BGE worker on CPU/CUDA, including warm latency and process resources."""
import argparse,json,os,statistics,time,threading,subprocess,platform
from pathlib import Path
from app.config import get_settings,PROJECT_ROOT
from app.model_clients.factory import embedding_client


def percentile(values,q):
    values=sorted(values);position=(len(values)-1)*q;low=int(position);high=min(low+1,len(values)-1)
    return values[low]+(values[high]-values[low])*(position-low)

class Resources:
    def __init__(self):self.rss=[];self.gpu=[];self.stop=threading.Event()
    def sample(self):
        while not self.stop.is_set():
            try:
                fields=Path('/proc/self/statm').read_text().split();self.rss.append(int(fields[1])*os.sysconf('SC_PAGE_SIZE')/1024**2)
            except OSError:pass
            self.stop.wait(.05)
    def sample_gpu(self):
        while not self.stop.is_set():
            try:
                r=subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3)
                if r.returncode==0:self.gpu.append([float(x.strip()) for x in r.stdout.splitlines()[0].split(',')])
            except (OSError,ValueError,subprocess.TimeoutExpired):pass
            self.stop.wait(.25)
    def start(self):
        self.threads=[threading.Thread(target=self.sample,daemon=True),threading.Thread(target=self.sample_gpu,daemon=True)]
        for t in self.threads:t.start()
    def finish(self):
        self.stop.set()
        for t in self.threads:t.join(timeout=4)


def main():
    p=argparse.ArgumentParser();p.add_argument('--device',choices=['cpu','cuda'],required=True);p.add_argument('--batch-size',type=int,default=1)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.batch_size<1:p.error('batch-size must be positive')
    import torch,numpy as np
    torch.set_num_threads(2)
    if a.device=='cuda' and not torch.cuda.is_available():raise RuntimeError('CUDA is unavailable')
    settings=get_settings().model_copy(update={'embedding_device':a.device,'embedding_batch_size':a.batch_size})
    cases=[json.loads(l) for l in (PROJECT_ROOT/'evaluation/datasets/market-agents-v1.jsonl').read_text().splitlines()]
    queries=[c['query'] for c in cases if c['scope']=='retrieval'][:20]
    texts=[embedding_client(settings).QUERY_INSTRUCTION+q for q in queries]*3
    encoder=embedding_client(settings);sampler=Resources();sampler.start()
    t=time.perf_counter();encoder.encode_query(queries[0]);cold=time.perf_counter()-t
    if a.device=='cuda':torch.cuda.synchronize();torch.cuda.reset_peak_memory_stats()
    timings=[];vectors=[];wall=time.perf_counter();cpu=time.process_time()
    for offset in range(0,len(texts),a.batch_size):
        batch=texts[offset:offset+a.batch_size]
        if a.device=='cuda':torch.cuda.synchronize()
        t=time.perf_counter();result=encoder.encode_documents(batch)
        if a.device=='cuda':torch.cuda.synchronize()
        elapsed=time.perf_counter()-t;timings.append({'queries':len(batch),'seconds':elapsed,'amortized_ms':1000*elapsed/len(batch)});vectors.extend(result)
    warm=time.perf_counter()-wall;cpu_percent=100*(time.process_time()-cpu)/warm
    sampler.finish();values=[t['amortized_ms'] for t in timings]
    report={'device':a.device,'batch_size':a.batch_size,'encodings':len(texts),'warm_batches':len(timings),
        'cold_first_query_seconds':cold,'warm_median_ms':statistics.median(values),'warm_p95_ms':percentile(values,.95),
        'warm_std_ms':statistics.pstdev(values),'throughput_queries_per_second':len(texts)/warm,
        'warm_process_cpu_percent_one_core_100':cpu_percent,'logical_cpu_count':os.cpu_count(),
        'peak_process_rss_mib':max(sampler.rss),'cuda_peak_allocated_mib':torch.cuda.max_memory_allocated()/1024**2 if a.device=='cuda' else None,
        'cuda_peak_reserved_mib':torch.cuda.max_memory_reserved()/1024**2 if a.device=='cuda' else None,
        'whole_device_peak_vram_mib':max((g[0] for g in sampler.gpu),default=None),'whole_device_peak_utilization_percent':max((g[1] for g in sampler.gpu),default=None),
        'torch':torch.__version__,'model':settings.embedding_model,'revision':settings.embedding_revision,
        'gpu':torch.cuda.get_device_name() if a.device=='cuda' else None,'platform':platform.platform(),
        'timings':timings,'notes':['Same20 queries repeated3times; one warmup excluded from latency statistics.','Batch timing is amortized per query, not interactive request latency.','RSS/whole-deviceGPU sampled50/250ms; peaks are observed, not continuous guarantees.','CPU100% means one occupied core; device GPU figures include other processes.']}
    a.output.mkdir(parents=True,exist_ok=True);np.save(a.output/'vectors.npy',np.asarray(vectors,dtype=np.float32))
    (a.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='timings'},indent=2))
if __name__=='__main__':main()
