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
quality_enabled=0
if test -f "$stage/deploy/setup-quality.sh"; then
    # Dependency installation can take minutes: keep the storefront online while preparing it.
    bash "$stage/deploy/setup-quality.sh" "$stage" > "$backup/quality-prepare.log" 2>&1
    quality_enabled=1
fi
cp -a "$app/backend/.env" "$backup/backend.env"
sources=(backend/app backend/knowledge web)
for directory in tests scripts; do
    test ! -d "$app/backend/$directory" || sources+=("backend/$directory")
done
tar --exclude='web/covers/uploads' -czf "$backup/code.tar.gz" -C "$app" "${sources[@]}"
cp -a "$app/venv" "$backup/venv"
systemctl stop private-store-quality 2>/dev/null || true
systemctl stop private-store
rollback() {
    echo 'Deployment failed; restoring previous code and dependencies' >&2
    systemctl stop private-store || true
    systemctl stop private-store-quality 2>/dev/null || true
    mkdir -p "$stage/rollback"
    tar -xzf "$backup/code.tar.gz" -C "$stage/rollback"
    rsync -a --delete "$stage/rollback/backend/app/" "$app/backend/app/"
    rsync -a --delete "$stage/rollback/backend/knowledge/" "$app/backend/knowledge/"
    for directory in tests scripts; do
        if test -d "$stage/rollback/backend/$directory"; then
            rsync -a --delete "$stage/rollback/backend/$directory/" "$app/backend/$directory/"
        fi
    done
    rsync -a --delete --exclude='covers/uploads/' "$stage/rollback/web/" "$app/web/"
    rsync -a --delete "$backup/venv/" "$app/venv/"
    chown -R storeapp:storeapp "$app/backend/app" "$app/backend/knowledge" "$app/web"
    systemctl start private-store || true
}
trap 'rollback' ERR
"$app/venv/bin/python" /usr/local/sbin/private-store-backup-db "$backup"
rsync -a --delete "$stage/backend/app/" "$app/backend/app/"
rsync -a --delete "$stage/backend/knowledge/" "$app/backend/knowledge/"
if test "$quality_enabled" = 1; then
    for directory in tests scripts; do
        mkdir -p "$app/backend/$directory"
        rsync -a --delete "$stage/backend/$directory/" "$app/backend/$directory/"
        chown -R storeapp:storeapp "$app/backend/$directory"
    done
fi
rsync -a --delete --exclude='covers/uploads/' "$stage/web/" "$app/web/"
"$app/venv/bin/pip" install -r "$stage/backend/requirements-server.txt" > "$backup/pip.log" 2>&1
chown -R storeapp:storeapp "$app/backend/app" "$app/backend/knowledge" "$app/web"
systemctl start private-store
healthy=0
for attempt in $(seq 1 30); do
    if curl --fail --silent --max-time 2 http://127.0.0.1:8001/api/v1/ready | "$app/venv/bin/python" -c 'import json,sys; result=json.load(sys.stdin); assert result["status"]=="ready" and all(result["checks"].values())' 2>/dev/null; then healthy=1; break; fi
    sleep 2
done
test "$healthy" = 1
if test "$quality_enabled" = 1; then
    systemctl enable --now private-store-quality
    systemctl is-active --quiet private-store-quality
fi
printf '%s\n' "$revision" > "$app/deployed-commit"
trap - ERR
echo "Deployed $revision; backup: $backup"
