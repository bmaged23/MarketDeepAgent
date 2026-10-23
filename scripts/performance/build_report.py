"""Publish measured aggregates and SVG; raw vectors/traces stay private."""
import json,statistics,html
from pathlib import Path
import numpy as np
from app.config import PROJECT_ROOT

def main():
    r=PROJECT_ROOT;private=r/'.release-local/performance';public=r/'docs/performance';public.mkdir(parents=True,exist_ok=True)
    names=['cpu-batch1','cuda-batch1','cuda-batch8'];data={n:json.loads((private/n/'summary.json').read_text()) for n in names}
    vectors={n:np.load(private/n/'vectors.npy') for n in names}
    reference=vectors[names[0]];agreement={}
    for n,v in vectors.items():
        cos=np.sum(reference*v,axis=1)/(np.linalg.norm(reference,axis=1)*np.linalg.norm(v,axis=1))
        agreement[n]=float(cos.min());assert cos.min()>.9999,'CPU/GPU vector disagreement'
    rows=[json.loads(l) for l in (r/'.evaluation-local/source-baseline/cases.jsonl').read_text().splitlines()]
    calls=[c for row in rows for c in row.get('calls',[]) if c['operation']=='chat']
    known=[c['usage'] for c in calls if c.get('usage')]
    usage={k:sum(u[k] for u in known if u.get(k) is not None) for k in ['input_tokens','output_tokens']}
    durations=sum(row['duration_seconds'] for row in rows)
    llm_seconds=sum(c['duration_seconds'] for c in calls)
    report={'embedding_configurations':data,'minimum_cosine_vs_cpu':agreement,
        'gpu_single_query_median_speedup':data[names[0]]['warm_median_ms']/data[names[1]]['warm_median_ms'],
        'source_baseline_call_analysis':{'cases':len(rows),'recorded_llm_calls':len(calls),'calls_with_usage':len(known),
            'tokens':usage,'sum_case_seconds':durations,'sum_recorded_llm_call_seconds':llm_seconds,'llm_share_of_sum_case_time':llm_seconds/durations,
            'scope':'Source GPU baseline; per-case durations overlap across workers and are not total experiment wall time. Cloud/network wait is included. Monetary cost not estimated without billing rates.'}}
    (public/'measurements.json').write_text(json.dumps(report,indent=2)+'\n')
    colors=['#94a3b8','#38bdf8','#34d399'];labels=['CPU · batch 1','GPU · batch 1','GPU · batch 8']
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="440" viewBox="0 0 1000 440" role="img" aria-labelledby="title desc">',
         '<title id="title">Measured MarketDeepAgent BGE performance</title><desc id="desc">Warm embedding latency and peak process RAM on identical queries. Batch timing is amortized per query.</desc>',
         '<rect width="1000" height="440" rx="18" fill="#0f172a"/>',
         '<g font-family="Arial,sans-serif" fill="#f1f5f9"><text x="30" y="38" font-size="23">MarketDeepAgent · measured embedding performance</text>',
         '<text x="30" y="66" font-size="14" fill="#cbd5e1">BGE-large-en-v1.5 · 60 encodings/configuration · GTX 1660 Ti · FP32</text>']
    for panel,(key,title,unit,maximum) in enumerate([('warm_median_ms','Warm median / query','ms',260),('peak_process_rss_mib','Peak process RAM','MiB',2200)]):
        x=30+panel*490
        svg.append(f'<text x="{x}" y="112" font-size="19">{title}</text>')
        for i,(name,label,color) in enumerate(zip(names,labels,colors)):
            y=148+i*75;value=data[name][key];width=350*value/maximum
            svg.append(f'<text x="{x}" y="{y}" font-size="14">{html.escape(label)}</text><rect x="{x}" y="{y+10}" width="{width:.2f}" height="22" rx="4" fill="{color}"/><text x="{x+width+8:.2f}" y="{y+27}" font-size="13">{value:.2f} {unit}</text>')
    svg+=['<text x="30" y="405" font-size="13" fill="#cbd5e1">Batch 8 = throughput measurement, not interactive response time. RAM = sampled process RSS.</text></g></svg>']
    (public/'embedding-comparison.svg').write_text('\n'.join(svg)+'\n')
    md=['# Performance measurements','','![CPU/GPU embeddings](../performance/embedding-comparison.svg)','','## Same-query CPU/GPU comparison','',
        '| Configuration | Warm median | Warm p95 | Queries/s | Peak RAM | Peak CUDA allocation | Mean CPU* |','|---|---:|---:|---:|---:|---:|---:|']
    for n,label in zip(names,labels):
        d=data[n];cuda='—' if d['cuda_peak_allocated_mib'] is None else f"{d['cuda_peak_allocated_mib']:.1f} MiB"
        md.append(f"| {label} | {d['warm_median_ms']:.2f} ms | {d['warm_p95_ms']:.2f} ms | {d['throughput_queries_per_second']:.2f} | {d['peak_process_rss_mib']:.1f} MiB | {cuda} | {d['warm_process_cpu_percent_one_core_100']:.1f}% |")
    md+=['',f"GPU single-query warm median was **{report['gpu_single_query_median_speedup']:.2f}× faster** in this benchmark. CPU/GPU cosine agreement exceeded {min(agreement.values()):.8f} (float32 rounding can report 1.0). Batch 8 timing is amortized; it excludes waiting to accumulate a batch and is not individual-user latency.",
        '', '*CPU 100% means one occupied logical core. RSS and whole-device GPU observations are sampled; device metrics include other processes. Each process warmed the same 20 queries repeated 3 times, with a separate startup query. Peak RAM includes model initialization. GPU allocation/reservation comes from PyTorch. These are worker measurements, not whole-stack requirements.',
        '', '## Agent/cloud bottleneck', '',f"The 100-case source GPU baseline recorded **{len(calls)} LLM calls**. Their summed durations accounted for **{100*llm_seconds/durations:.1f}%** of summed per-case elapsed time, including network/provider wait. Cases overlap across 2 workers, so these sums are not experiment wall time. Recorded usage: **{usage['input_tokens']:,} input tokens**, **{usage['output_tokens']:,} output tokens**; usage is available on {len(known)}/{len(calls)} calls. No invoice/currency cost is inferred.",
        '', 'The main gpt-oss:120b model is hosted on Ollama Cloud. Local GPU resources are used for BGE, not for a 120B local model. The public portable image uses CPU embeddings; the native CUDA setup is measured separately. GPU embedding speedup is not an equal whole-agent speedup.',
        '', '## Implementation changes and limits', '', '- BGE weights are pinned and bundled in the candidate image, avoiding a first-run model download.',
        '- Provisioning runs in a short-lived process so its model memory is released before the server starts. The existing per-process model cache avoids repeated loads.',
        '- Current user cart instructions are retained across delegation; owned SQL delivery status avoids unnecessary review clarification. Explicit quote preparation does not authorize checkout.',
        '- Controlled embedding benchmarks and final CPU/GPU workflow measurements are complete. The published container uses CPU; native GPU support is verified separately. No GPU-container or universal compatibility claim.',
        '', '## Reproduce', '', '```bash','python -m scripts.performance.benchmark_embeddings --device cpu --batch-size 1 --output .release-local/performance/cpu-batch1',
        '# Run these with the CUDA environment:','python -m scripts.performance.benchmark_embeddings --device cuda --batch-size 1 --output .release-local/performance/cuda-batch1',
        'python -m scripts.performance.benchmark_embeddings --device cuda --batch-size 8 --output .release-local/performance/cuda-batch8',
        'python -m scripts.performance.build_report','```','','[Machine-readable measurements](../performance/measurements.json). Raw vectors and full agent traces stay ignored.']
    guide=r/'docs/guides/PERFORMANCE.md'
    previous=guide.read_text() if guide.exists() else ''
    marker='## Final release measurements'
    if marker in previous:md+=['',previous[previous.index(marker):].rstrip()]
    guide.write_text('\n'.join(md)+'\n')
    print('Published measured JSON, SVG and report; vector agreement verified.')
if __name__=='__main__':main()
