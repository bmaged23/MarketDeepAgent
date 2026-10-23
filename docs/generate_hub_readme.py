"""Generate Docker Hub's copy from maintained guides, with absolute GitHub links."""
from pathlib import Path
import re
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]
GITHUB='https://github.com/bmaged23/MarketDeepAgent/blob/main/'
RAW='https://raw.githubusercontent.com/bmaged23/MarketDeepAgent/main/'

def section(path):
    source=ROOT/path;fenced=False;lines=[]
    def link(match):
        label,target=match.groups()
        if target.startswith(('http://','https://','mailto:','#')):return match.group()
        relative,_,fragment=target.partition('#')
        local=(source.parent/relative).resolve()
        relative=local.relative_to(ROOT).as_posix()
        base=RAW if label.startswith('!') else GITHUB
        return label+'('+base+quote(relative,safe='/')+('#'+fragment if fragment else '')+')'
    for line in source.read_text().splitlines():
        if line.startswith('```'):fenced=not fenced
        if not fenced:
            line=re.sub(r'(!?\[[^\]]+\])\(([^)]+)\)',link,line)
            if line.startswith('#'):line='#'+line
        lines.append(line)
    return '\n'.join(lines)

def main():
    body='''# MarketDeepAgent

**[GitHub source, demo and complete project README](https://github.com/bmaged23/MarketDeepAgent)**

An AI grocery marketplace with retrieval, cart and customer agents, hybrid product search, persistent conversations and explicitly confirmed orders. The portable CPU image includes the seeded catalog and pinned BGE embedding weights; the main LLM runs on your Ollama Cloud account.

'''+ '\n\n'.join(section(Path(p)) for p in ['docs/DOCKER.md','docs/EVALUATION.md','docs/PERFORMANCE.md'])+'\n'
    assert len(body)<=25000,'Hub description exceeds limit; shorten the guides without truncating commands'
    (ROOT/'docs/DOCKERHUB_README.md').write_text(body)
    print('Generated canonical Docker Hub README:',len(body),'characters')
if __name__=='__main__':main()
