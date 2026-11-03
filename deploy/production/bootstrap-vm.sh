#!/usr/bin/env bash
# Run as root after transferring the approved release archive into the private root.
set -euo pipefail
umask 077
test "$#" -eq 1
archive_sha=$1
[[ "$archive_sha" =~ ^[0-9a-f]{64}$ ]]
root=/srv/attackscope/production
cd "$root"
printf '%s  release.tar.gz\n' "$archive_sha" | sha256sum --check
test ! -e release
if docker volume inspect attackscope-production_attackscope-data >/dev/null 2>&1; then
    printf '%s\n' 'Production volume already exists; use the update procedure.' >&2
    exit 1
fi
install -d -m 700 -o 1002 -g 1002 release run
install -d -m 700 -o 10003 -g 10003 collector-state
install -d -m 700 secrets backups
install -d -m 755 logs logs/nginx
tar --extract --gzip --file release.tar.gz --directory release --no-same-owner
cd release
chown -R 1002:1002 .
sha256sum --check SHA256SUMS
docker load --input images.tar
for kind in backend frontend; do
    expected=$(python3 -c 'import json,sys; print(json.load(open("MANIFEST.json"))[sys.argv[1]+"_image"])' "$kind")
    test "$(docker image inspect --format '{{.Id}}' "attackscope-$kind:production-0.1-20261103")" = "$expected"
done
docker compose config --quiet
docker compose up --no-build --pull never --wait --wait-timeout 120 backend frontend
container=attackscope-production-backend-1
docker exec "$container" python -m attackscope.cli create-host --name production-vm > "$root/host.json"
host=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["host_id"])' "$root/host.json")
for kind in ssh http; do
    docker exec "$container" python -m attackscope.cli create-source --host-id "$host" --kind "$kind" --token-file "/data/secrets/$kind.token"
done
docker exec "$container" python -c 'import json,os; from pathlib import Path; p=Path("/data/secrets"); (p/"sources.json").write_text(json.dumps({kind:(p/(kind+".token")).read_text().strip() for kind in ("ssh","http")})); os.chmod(p/"sources.json",0o600)'
docker cp "$container:/data/secrets/sources.json" "$root/secrets/sources.json"
chown 10003:10003 "$root/secrets/sources.json"
chmod 600 "$root/secrets/sources.json"
docker compose run --rm --no-deps collector validate --skip-healthchecks /etc/vector/vector.yaml
printf '%s\n' PRODUCTION_DB_AND_PRIVATE_SOURCES_READY
