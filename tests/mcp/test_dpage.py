from getgather.mcp import dpage


def test_is_incognito_request_respects_header(monkeypatch):
    monkeypatch.setattr(
        dpage,
        "get_auth_user",
        lambda: type("AuthUserStub", (), {"auth_provider": "google"})(),
    )

    assert dpage.is_incognito_request({"x-incognito": "1"}) is True


def test_is_incognito_request_defaults_to_incognito_for_noauth(monkeypatch):
    monkeypatch.setattr(
        dpage,
        "get_auth_user",
        lambda: type("AuthUserStub", (), {"auth_provider": "noauth"})(),
    )

    assert dpage.is_incognito_request({}) is True


def test_is_incognito_request_is_false_without_header_or_noauth(monkeypatch):
    monkeypatch.setattr(
        dpage,
        "get_auth_user",
        lambda: type("AuthUserStub", (), {"auth_provider": "google"})(),
    )

    assert dpage.is_incognito_request({}) is False
