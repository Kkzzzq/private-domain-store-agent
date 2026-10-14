#!/bin/bash
# Installed separately as /usr/local/sbin/private-store-receive, owned by root.
set -euo pipefail
umask 077
if [[ ! ${SSH_ORIGINAL_COMMAND:-} =~ ^deploy\ ([0-9a-f]{40})$ ]]; then
    echo 'Only deploy <commit SHA> is allowed' >&2; exit 1
fi
revision=${BASH_REMATCH[1]}
exec 9>/run/lock/private-store-deploy.lock
flock -w 600 9
app=/opt/private-store
backup=/root/private-store-backups/$(date +%Y%m%d-%H%M%S)-${revision:0:12}
stage=$(mktemp -d /opt/private-store-stage.XXXXXX)
trap 'rm -rf -- "$stage"' EXIT
cat > "$stage/source.tar"
tar -xf "$stage/source.tar" -C "$stage"
test -f "$stage/backend/app/main.py"
test -f "$stage/web/index.html"
test -f "$stage/backend/requirements-server.txt"
/opt/private-store/venv/bin/python -m compileall -q "$stage/backend/app"
mkdir -p "$backup"
tar --exclude='web/covers/uploads' -czf "$backup/code.tar.gz" -C "$app" backend/app backend/knowledge web
cp -a "$app/venv" "$backup/venv"
systemctl stop private-store
rollback() {
    echo 'Deployment failed; restoring previous code and dependencies' >&2
    systemctl stop private-store || true
    mkdir -p "$stage/rollback"
    tar -xzf "$backup/code.tar.gz" -C "$stage/rollback"
    rsync -a --delete "$stage/rollback/backend/app/" "$app/backend/app/"
    rsync -a --delete "$stage/rollback/backend/knowledge/" "$app/backend/knowledge/"
    rsync -a --delete --exclude='covers/uploads/' "$stage/rollback/web/" "$app/web/"
    rsync -a --delete "$backup/venv/" "$app/venv/"
    chown -R storeapp:storeapp "$app/backend/app" "$app/backend/knowledge" "$app/web"
    systemctl start private-store || true
}
trap 'rollback' ERR
"$app/venv/bin/python" - "$backup/store.db" <<'PY'
import sqlite3,sys
source=sqlite3.connect('file:/opt/private-store/backend/data/store.db?mode=ro',uri=True)
target=sqlite3.connect(sys.argv[1]); source.backup(target)
assert target.execute('PRAGMA quick_check').fetchone()[0]=='ok'
target.close(); source.close()
PY
rsync -a --delete "$stage/backend/app/" "$app/backend/app/"
rsync -a --delete "$stage/backend/knowledge/" "$app/backend/knowledge/"
rsync -a --delete --exclude='covers/uploads/' "$stage/web/" "$app/web/"
"$app/venv/bin/pip" install -r "$stage/backend/requirements-server.txt" > "$backup/pip.log" 2>&1
chown -R storeapp:storeapp "$app/backend/app" "$app/backend/knowledge" "$app/web"
systemctl start private-store
healthy=0
for attempt in $(seq 1 30); do
    if curl --fail --silent --max-time 2 http://127.0.0.1:8001/api/v1/health | "$app/venv/bin/python" -c 'import json,sys; assert json.load(sys.stdin)["status"]=="ok"' 2>/dev/null; then healthy=1; break; fi
    sleep 2
done
test "$healthy" = 1
printf '%s\n' "$revision" > "$app/deployed-commit"
trap - ERR
echo "Deployed $revision; backup: $backup"
