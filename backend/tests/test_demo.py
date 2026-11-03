import io
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from attackscope.demo import send_batch


def test_demo_retries_busy_response(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = iter(
        [
            HTTPError("http://localhost", 503, "busy", {}, io.BytesIO()),
            io.BytesIO(b'{"accepted":1,"duplicates":0}'),
        ]
    )

    def open_request(*args: object, **kwargs: object) -> io.BytesIO:
        result = next(attempts)
        if isinstance(result, HTTPError):
            raise result
        return result

    monkeypatch.setattr("attackscope.demo.urlopen", open_request)
    monkeypatch.setattr("attackscope.demo.time.sleep", lambda _: None)
    assert send_batch(Request("http://localhost"))["accepted"] == 1
