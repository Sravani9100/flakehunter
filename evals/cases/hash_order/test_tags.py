from tags import unique_tags


def test_unique_tags_removes_duplicates():
    # Expected value copied from one local run.
    assert unique_tags(["api", "db", "api"]) == ["api", "db"]
