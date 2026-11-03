#!/usr/bin/env bash
set -euo pipefail
cd /srv/attackscope/production/release
docker compose config --quiet
docker compose run --rm --no-deps collector validate --skip-healthchecks /etc/vector/vector.yaml
# The operator must configure a dedicated Nginx JSON log before starting collection.
docker compose up --no-build --pull never --wait --wait-timeout 120
install -d -m 755 /usr/local/libexec/attackscope
install -d -m 700 /etc/attackscope
install -m 755 deploy/production/ops.py /usr/local/libexec/attackscope/ops.py
install -m 644 deploy/production/attackscope-maintenance@.service /etc/systemd/system/attackscope-maintenance@.service
for name in attackscope-backup.timer attackscope-check.timer attackscope-restore-check.timer attackscope-logrotate.timer; do
    install -m 644 "deploy/production/$name" "/etc/systemd/system/$name"
done
install -m 644 deploy/production/logrotate.conf /etc/attackscope/logrotate.conf
systemd-analyze verify /etc/systemd/system/attackscope-maintenance@.service /etc/systemd/system/attackscope-*.timer
logrotate --debug /etc/attackscope/logrotate.conf
systemctl daemon-reload
systemctl start attackscope-maintenance@backup.service
systemctl start attackscope-maintenance@restore-check.service
systemctl enable --now attackscope-backup.timer attackscope-check.timer attackscope-restore-check.timer attackscope-logrotate.timer
printf '%s\n' PRODUCTION_COLLECTION_AND_MAINTENANCE_STARTED
