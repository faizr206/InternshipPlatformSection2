import pytest


@pytest.fixture(autouse=True)
def _own_fixture_data(monkeypatch):
    """The Sprint 1-3 tests use our own synthetic set (6 profiles, 6 listings with built-in
    test cases). tests/test_p01p03_data.py switches to the P01-P03 export explicitly."""
    monkeypatch.setenv("DATA_SOURCE", "fixtures")
