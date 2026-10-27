import pytest


@pytest.fixture(autouse=True)
def no_real_second_listener(monkeypatch):
    """A shell that sourced ../.env must not send test transcripts to Baseten: the second listener needs this key."""
    monkeypatch.delenv("BASETEN_API_KEY", raising=False)
