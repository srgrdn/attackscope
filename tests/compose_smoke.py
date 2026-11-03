"""Local Compose integration check; uses only the Python standard library."""

import argparse
import json
import subprocess
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8180")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    with urlopen(base + "/", timeout=5) as response:
        assert response.status == 200 and b"AttackScope" in response.read()
    with urlopen(base + "/api/v1/health/ready", timeout=5) as response:
        assert json.load(response)["status"] == "ready"
    for path in ("/api/v1/ingest/events", "/api/v1/unknown"):
        try:
            urlopen(base + path, timeout=5)
        except HTTPError as error:
            assert error.code == 404
        else:
            raise AssertionError("Ingestion must not be exposed by the UI")
    try:
        urlopen(Request(base + "/", headers={"Host": "untrusted.example"}), timeout=5)
    except HTTPError as error:
        assert error.code == 421
    else:
        raise AssertionError("Untrusted Host accepted")
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "backend",
        "python",
        "-m",
        "attackscope.demo",
        "--run-name",
        "smoke",
    ]
    first = json.loads(
        subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=30
        ).stdout
    )
    second = json.loads(
        subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=30
        ).stdout
    )
    assert first["accepted"] + first["duplicates"] == 8
    assert second["accepted"] == 0 and second["duplicates"] == 8
    with urlopen(
        base + "/api/v1/events?" + urlencode(first["query"]), timeout=5
    ) as response:
        page = json.load(response)
    assert len(page["items"]) == 8
    assert {item["source"] for item in page["items"]} == {"ssh", "http", "firewall"}
    text = json.dumps(page)
    assert "discard-this" not in text and "not-a-real-secret" not in text
    print(
        "Compose smoke passed: UI, readiness, isolation, authenticated ingestion, redaction, dedup, read API"
    )


if __name__ == "__main__":
    main()
