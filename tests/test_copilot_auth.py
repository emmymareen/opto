
import httpx

from opto.copilot_auth import CopilotSession, _token_endpoint, _extract_token


def test_token_endpoint_default():
    assert _token_endpoint("github.com") == (
        "https://api.github.com/copilot_internal/v2/token"
    )


def test_token_endpoint_enterprise():
    assert _token_endpoint("ghe.acme.com") == (
        "https://ghe.acme.com/api/v3/copilot_internal/v2/token"
    )


def test_extract_token_apps_json():
    data = {"github.com:Iv1.abc": {"oauth_token": "ghu_secret", "user": "x"}}
    assert _extract_token(data) == "ghu_secret"


def test_extract_token_hosts_json():
    data = {"github.com": {"oauth_token": "ghu_other"}}
    assert _extract_token(data) == "ghu_other"


def _mock_client(captured: dict, endpoint_api: str):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "token": "tid=abc;exp=9999999999",
                "expires_at": 9999999999,
                "endpoints": {"api": endpoint_api},
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_business_endpoint_discovered():
    captured: dict = {}
    s = CopilotSession(oauth_token="ghu_x")
    client = _mock_client(captured, "https://api.business.githubcopilot.com")
    base = s.api_base(client=client)
    assert base == "https://api.business.githubcopilot.com"
    assert captured["auth"] == "token ghu_x"
    assert captured["url"].endswith("/copilot_internal/v2/token")


def test_auth_headers_include_client_identity():
    captured: dict = {}
    s = CopilotSession(oauth_token="ghu_x")
    client = _mock_client(captured, "https://api.individual.githubcopilot.com")
    headers = s.auth_headers(client=client)
    assert headers["Authorization"].startswith("Bearer ")
    for required in ("Editor-Version", "Editor-Plugin-Version", "Copilot-Integration-Id"):
        assert required in headers


def test_token_cached_until_expiry():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json={"token": "t", "expires_at": 9999999999,
                  "endpoints": {"api": "https://api.githubcopilot.com"}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    s = CopilotSession(oauth_token="ghu_x")
    s.bearer(client=client)
    s.bearer(client=client)
    s.api_base(client=client)
    assert calls["n"] == 1  # only exchanged once, then cached
