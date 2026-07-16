"""Regression coverage for the test harness itself: client_fixture must never
run the app's real startup lifespan (which seeds — and on schema drift,
recreates — the real custody.db file via database.connection.engine)."""

import pytest


def test_client_fixture_never_invokes_real_seed_data(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    import main as main_module

    calls: list[None] = []
    monkeypatch.setattr(
        main_module, "ensure_default_seed_data", lambda session: calls.append(None)
    )

    # Instantiate client_fixture now, after the monkeypatch is in place, so
    # that if the real lifespan ran it would call our patched stand-in
    # instead of the genuine seeding function.
    client = request.getfixturevalue("client_fixture")

    assert calls == []

    response = client.get("/api/v1/health")
    assert response.status_code == 200
