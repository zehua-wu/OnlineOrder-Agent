from app.evaluation.run import evaluate_suite, percentile, ratio, wilson


async def test_offline_regression_and_metrics_distinguish_business_failure():
    report = await evaluate_suite()
    assert report["counts"]["scenarios"] == 8
    assert report["counts"]["business_tasks"] == 6
    assert report["metrics"]["safety_case_pass_rate"] == 1
    assert report["metrics"]["expected_outcome_pass_rate"] == 1
    assert report["metrics"]["task_completion_rate"] == 1
    assert report["metrics"]["tool_success_rate"] < 1
    assert report["metrics"]["write_success_rate"] == 0.5
    assert report["metrics"]["menu_recall_at_3_macro"] == 1
    assert report["metrics"]["memory_recall_at_8"] == 1
    assert report["metrics"]["input_tokens"] == 0
    assert report["metrics"]["task_completion_wilson_95_interval"][0] < 0.8


def test_metrics_handle_empty_denominators_and_small_samples():
    assert ratio(0, 0) is None
    assert percentile([], 0.95) is None
    assert percentile([5, 1, 2], 0.5) == 2
    assert wilson(0, 0) is None
    assert wilson(8, 8)[1] == 1
