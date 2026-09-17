from unittest.mock import patch

from fastapi.testclient import TestClient

from promptchived.main import app


def empty_search_result() -> dict:
    return {
        "items": [],
        "page": 1,
        "per_page": 20,
        "mode": "hybrid",
        "embedding_coverage": 1.0,
        "notice": None,
    }


def test_search_form_accepts_empty_optional_filters():
    client = TestClient(app)
    with patch("promptchived.main.search", return_value=empty_search_result()) as search_mock:
        response = client.get(
            "/search",
            params={"q": "overalls", "mode": "hybrid", "provider": "", "role": ""},
        )

    assert response.status_code == 200
    assert "No matching results." in response.text
    assert search_mock.call_args.kwargs["provider"] is None
    assert search_mock.call_args.kwargs["role"] is None


def test_english_is_default_and_language_choice_is_remembered():
    client = TestClient(app)

    english = client.get("/search")
    assert english.status_code == 200
    assert '<html lang="en">' in english.text
    assert "Search your entire archive" in english.text

    switched = client.post(
        "/language",
        data={"language": "id", "next_url": "/search"},
        follow_redirects=True,
    )
    assert switched.status_code == 200
    assert '<html lang="id">' in switched.text
    assert "Cari seluruh arsip" in switched.text


def test_language_redirect_rejects_external_target():
    client = TestClient(app)
    response = client.post(
        "/language",
        data={"language": "en", "next_url": "//example.com"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
