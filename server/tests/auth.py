"""The server key the tests run with: conftest puts it in HALLWISE_TOKEN, and clients send AUTH."""

TOKEN = "test-key-0123456789abcdefghijklmnop"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
