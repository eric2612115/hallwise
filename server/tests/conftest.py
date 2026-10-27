import pytest
from auth import TOKEN


@pytest.fixture(autouse=True)
def no_real_second_listener(monkeypatch):
    """A shell that sourced ../.env must not send test transcripts to Baseten: the second listener needs this key."""
    monkeypatch.delenv("BASETEN_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def server_key(monkeypatch):
    """Every app under test has a known key (a real one from ../.env never reaches the tests) and answers to the
    test client's host name."""
    monkeypatch.setenv("HALLWISE_TOKEN", TOKEN)
    monkeypatch.setenv("HALLWISE_HOSTS", "testserver")
    monkeypatch.delenv("HALLWISE_INSECURE", raising=False)
    monkeypatch.delenv("HALLWISE_BIND", raising=False)
