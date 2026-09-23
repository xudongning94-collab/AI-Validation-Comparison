from bid_compare_agent.utils.text import normalize_text


def test_normalize_text():
    assert normalize_text("  A\t B　C  ") == "A B C"
