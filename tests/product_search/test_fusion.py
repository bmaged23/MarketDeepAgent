import pytest
from app.product_search.rank_fusion import weighted_sum, normalize_scores, reciprocal_rank_fusion
from app.utils.text import keyword_query


def test_weighted_sum_normalizes_incompatible_scales():
    result = weighted_sum([(1,-100),(2,-50),(3,-1)], [(3,0.95),(2,0.70),(1,0.45)])
    scores = dict(result)
    assert scores[1] == pytest.approx(0.5)
    assert scores[3] == pytest.approx(0.5)
    assert scores[2] == pytest.approx(0.5*(49/99)+0.25)


def test_weights_can_favor_semantic_matches():
    assert weighted_sum([(1,-2),(2,-1)],[(2,0.9),(1,0.2)],0.2,0.8)[0][0] == 2


def test_empty_equal_and_singleton_scores():
    assert weighted_sum([],[]) == []
    assert dict(weighted_sum([(1,-1)],[])) == {1:0.5}
    assert normalize_scores([(1,0),(2,0)]) == {1:1.0,2:1.0}


def test_rrf_rewards_agreement_and_has_stable_ties():
    assert reciprocal_rank_fusion([(1,2),(2,1)],[(2,0.9),(3,0.2)])[0][0] == 2
    assert [p for p,_ in reciprocal_rank_fusion([(2,1)],[(1,1)])] == [1,2]


def test_fts_input_is_tokenized_not_executed():
    assert keyword_query('tea OR "coffee" * - (price:100)') == '"tea" OR "or" OR "coffee" OR "price" OR "100"'
