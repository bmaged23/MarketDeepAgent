"""Keep coordinator response routes visible when architecture diagrams are edited."""
from pathlib import Path
import xml.etree.ElementTree as ET
from docs.system_diagrams import generate


def test_specialist_responses_reach_coordinator_and_browser(tmp_path):
    generate(tmp_path)
    root=ET.parse(tmp_path/'architecture.svg').getroot()
    edges={(g.get('data-from'),g.get('data-to'),g.get('data-kind')) for g in root.iter() if g.get('data-from')}
    for specialist in ('retrieval','cart','memory'):
        assert ('customer',specialist,'request') in edges
        assert (specialist,'customer','response') in edges
    assert ('customer','api','response') in edges
    assert ('api','browser','response') in edges
    for source,target in [('vectors','search'),('sql','cart'),('sql','memory'),('search','retrieval')]:
        assert (source,target,'response') in edges


def test_retrieval_returns_evidence_and_can_search_again(tmp_path):
    generate(tmp_path)
    root=ET.parse(tmp_path/'architecture-retrieval.svg').getroot()
    edges={(g.get('data-from'),g.get('data-to'),g.get('data-kind')) for g in root.iter() if g.get('data-from')}
    assert ('coverage','tasks','request') in edges
    assert ('coverage','output','response') in edges
    assert ('output','customer','response') in edges
