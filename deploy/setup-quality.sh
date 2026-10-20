#!/bin/bash
# Prepare an independent test runtime without expanding the web API runtime.
set -euo pipefail
stage=${1:?staged source root required}
app=/opt/private-store
test -f "$stage/backend/requirements-e2e.txt"
test -f "$stage/backend/tests/conftest.py"
test -f "$stage/deploy/private-store-quality.service"
if [[ ! -x "$app/qa-venv/bin/python" ]]; then
    "$app/venv/bin/python" -m venv "$app/qa-venv"
fi
signature=$(cat "$stage/backend/requirements.txt" "$stage/backend/requirements-e2e.txt" | sha256sum | cut -d' ' -f1)
if [[ ! -f "$app/qa-venv/source-requirements.sha256" ]] || [[ $(cat "$app/qa-venv/source-requirements.sha256") != "$signature" ]]; then
    "$app/qa-venv/bin/pip" install -r "$stage/backend/requirements-e2e.txt"
    PLAYWRIGHT_BROWSERS_PATH="$app/qa-browsers" "$app/qa-venv/bin/python" -m playwright install --with-deps --only-shell chromium
    chown -R storeapp:storeapp "$app/qa-browsers"
    printf '%s\n' "$signature" > "$app/qa-venv/source-requirements.sha256"
fi
# The deploy receiver uses umask 077; the service group still needs read/execute access.
chown -R root:storeapp "$app/qa-venv"
chmod -R g+rX "$app/qa-venv"
install -m 644 "$stage/deploy/private-store-quality.service" /etc/systemd/system/private-store-quality.service
systemctl daemon-reload
# The receiver starts the worker only after the matching code is installed and healthy.
