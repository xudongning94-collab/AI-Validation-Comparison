from bid_compare_agent.compare.text_similarity import TextCompareConfig, normalize_for_compare


def test_normalize_for_compare_ignores_spacing_and_punctuation():
    assert normalize_for_compare("  本系统，支持 AI / 智能校验。 ") == "本系统支持ai智能校验"


def test_text_compare_config_rejects_invalid_thresholds():
    try:
        TextCompareConfig(medium_threshold=0.9, high_threshold=0.8)
    except ValueError as exc:
        assert "medium <= high" in str(exc)
    else:
        raise AssertionError("expected ValueError")
