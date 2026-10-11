import pytest
from app.product_search.evaluation import retrieval_metrics, compare_weights


def test_retrieval_metrics_use_rank_and_relevant_set():
    metrics=retrieval_metrics([9,2,3],[2,3,4],3)
    assert metrics['recall_at_k'] == pytest.approx(2/3)
    assert metrics['precision_at_k'] == pytest.approx(2/3)
    assert metrics['reciprocal_rank'] == 0.5
    assert metrics['ndcg_at_k'] == pytest.approx((1/1.584962500721156 + 0.5)/(1 + 1/1.584962500721156 + 0.5))
    assert retrieval_metrics([],[],3) == {'recall_at_k':0,'precision_at_k':0,'reciprocal_rank':0,'ndcg_at_k':0}


def test_ndcg_rewards_relevant_items_earlier_and_deduplicates():
    assert retrieval_metrics([2,3,9],[2,3],3)['ndcg_at_k'] == 1
    assert retrieval_metrics([9,2,3],[2,3],3)['ndcg_at_k'] < 1
    assert retrieval_metrics([2,2],[2],2)['ndcg_at_k'] == 1


class FakeSearch:
    fusion_method = 'rrf'
    bm25_weight = 0.5
    vector_weight = 0.5

    def __init__(self, degraded=False, vector_error=False):
        self.degraded, self.vector_error = degraded, vector_error

    def search(self, query, filters, limit, mode):
        if mode == 'vector' and self.vector_error:
            raise RuntimeError('Vector unavailable')
        relevant_first = mode == 'vector' or (mode == 'hybrid' and self.vector_weight >= 0.6)
        ids = [1,2] if relevant_first else [2,1]
        return {'degraded': self.degraded and mode == 'hybrid', 'results': [
            {'product': {'product_id': i, 'name': f'Product {i}'}, 'score': 1/rank,
             'sources': [mode]} for rank,i in enumerate(ids,1)]}


def test_weight_sweep_selects_rank_quality_and_restores_settings():
    service = FakeSearch()
    report = compare_weights(service, [{'query':'test','relevant_product_names':['Product 1']}], {'Product 1':1},2)
    assert report['valid']
    assert len(report['weights']) == 11
    assert all(row['vector_weight'] >= 0.6 for row in report['best_weights'])
    assert service.fusion_method == 'rrf'
    assert (service.bm25_weight, service.vector_weight) == (0.5,0.5)


def test_weight_sweep_does_not_recommend_degraded_search():
    report = compare_weights(FakeSearch(degraded=True),
        [{'query':'test','relevant_product_names':['Product 1']}], {'Product 1':1},2)
    assert not report['valid']
    assert report['best_weights'] == []


def test_weight_sweep_fails_when_vector_baseline_unavailable():
    service = FakeSearch(vector_error=True)
    with pytest.raises(RuntimeError):
        compare_weights(service, [{'query':'test','relevant_product_names':['Product 1']}], {'Product 1':1},2)
    assert service.fusion_method == 'rrf'


def test_custom_weights_include_pure_baselines_and_deduplicate():
    report = compare_weights(FakeSearch(),
        [{'query':'test','relevant_product_names':['Product 1']}], {'Product 1':1},2,
        weights=[0.3,0.5,0.7,0.5])
    assert set(report['baselines']) == {'bm25','vector'}
    assert [row['bm25_weight'] for row in report['weights']] == [0.3,0.5,0.7]
    assert all(row['bm25_weight'] + row['vector_weight'] == pytest.approx(1) for row in report['weights'])


@pytest.mark.parametrize('weights', [[],[-0.1],[1.1],[float('nan')],[float('inf')]])
def test_invalid_custom_weights_are_rejected(weights):
    with pytest.raises(ValueError):
        compare_weights(FakeSearch(),[],{},5,weights=weights)
