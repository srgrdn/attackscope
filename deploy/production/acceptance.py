#!/usr/bin/python3
"""Operator-approved live acceptance: harmless HTTP probes and scoped fault recovery."""

import subprocess
import time
import os
import signal
from collections.abc import Callable
from uuid import uuid4

from ops import BACKEND, COLLECTOR, docker, inspect


def wait_for(predicate: Callable[[], bool], description: str, timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(1)
    raise RuntimeError("Timed out: " + description)


def count(marker: str) -> int:
    code = """import sqlite3,sys
c=sqlite3.connect('/data/attackscope.db')
query=("SELECT count(*) FROM events WHERE source='http' "
       "AND json_extract(attributes,'$.user_agent')=?")
print(c.execute(query,(sys.argv[1],)).fetchone()[0])
"""
    return int(docker("exec", BACKEND, "python", "-c", code, marker).strip())


def probe(marker: str) -> None:
    subprocess.run(
        [
            "curl",
            "--silent",
            "--show-error",
            "--max-time",
            "10",
            "--output",
            "/dev/null",
            "--user-agent",
            marker,
            "http://127.0.0.1/?attackscope_probe=SAFE_QUERY_PLACEHOLDER",
        ],
        check=True,
        capture_output=True,
    )


def main() -> None:
    auth_code = """import json,sqlite3
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
c=sqlite3.connect('/data/attackscope.db')
query="SELECT count(*) FROM events WHERE source_reference LIKE 'demo:%'"
assert c.execute(query).fetchone()[0]==0
query="SELECT count(*) FROM events WHERE source='ssh' AND source_reference IS NOT NULL"
assert c.execute(query).fetchone()[0]>0
saved=' '.join(str(row) for row in c.execute('SELECT attributes,safe_original FROM events'))
placeholders=('ATTACKSCOPE_QUERY_PLACEHOLDER','ATTACKSCOPE_HEADER_PLACEHOLDER',
              'ATTACKSCOPE_COOKIE_PLACEHOLDER')
assert all(value not in saved for value in placeholders)
tokens=json.loads(Path('/data/secrets/sources.json').read_text())
def send(events,token=None,expected=200):
    headers={'Content-Type':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    try:
        request=Request('http://127.0.0.1:8001/api/v1/ingest/events',
                        data=json.dumps(events).encode(),headers=headers)
        with urlopen(request,timeout=10) as response:
            assert expected==200
            return json.load(response)
    except HTTPError as error:
        assert error.code==expected,(error.code,expected)
send([],expected=401)
event={'transport_version':1,'source':'ssh',
       'host_id':'00000000-0000-0000-0000-000000000000',
       'payload':{'timestamp':datetime.now(timezone.utc).isoformat(),
                  'src_ip':'127.0.0.1','outcome':'success'}}
send([event],tokens['ssh'],403)
event.pop('host_id')
send([event],tokens['http'],403)
query=("SELECT source_reference,safe_original FROM events "
       "WHERE source='ssh' AND source_reference IS NOT NULL LIMIT 1")
reference,payload=c.execute(query).fetchone()
event={'transport_version':1,'source':'ssh','source_reference':reference,
       'payload':json.loads(payload)}
result=send([event],tokens['ssh'])
assert result['accepted']==0 and result['duplicates']==1,result
print('Source authentication, host/kind binding, real SSH replay and redaction verified')
"""
    print(docker("exec", BACKEND, "python", "-c", auth_code).strip())
    marker = "AttackScope recovery check " + uuid4().hex[:12]
    assert count(marker) == 0
    started = inspect(COLLECTOR)["State"]["StartedAt"]
    try:
        docker("stop", "--time", "20", BACKEND)
        for _ in range(3):
            probe(marker)
        time.sleep(3)
        # Docker's kill API marks a manual stop; signal the inspected process to
        # simulate an actual crash and exercise the daemon's restart policy.
        process = inspect(COLLECTOR)
        assert process["Name"] == "/" + COLLECTOR and process["State"]["Running"]
        pid = int(process["State"]["Pid"])
        assert pid > 1
        os.kill(pid, signal.SIGKILL)
        wait_for(
            lambda: (
                inspect(COLLECTOR)["State"]["Running"]
                and inspect(COLLECTOR)["State"]["StartedAt"] != started
            ),
            "collector auto-restart",
        )
    finally:
        docker("start", BACKEND)
    wait_for(
        lambda: inspect(BACKEND)["State"].get("Health", {}).get("Status") == "healthy",
        "backend readiness",
    )
    wait_for(lambda: count(marker) >= 3, "buffer delivery after restart")
    assert count(marker) == 3, "Unexpected replay duplicates"
    print("Backend outage + collector crash: three HTTP events recovered without stored duplicates")


if __name__ == "__main__":
    main()
