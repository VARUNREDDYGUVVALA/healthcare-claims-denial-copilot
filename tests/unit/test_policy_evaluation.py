from evaluation.rag.evaluate_policies import evaluate_golden_cases


def test_golden_policy_citations():
    results = evaluate_golden_cases()
    assert results
    assert [item["actual"] for item in results] == [item["expected"] for item in results]
