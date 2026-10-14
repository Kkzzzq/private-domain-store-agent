#!/bin/bash
set -euo pipefail
cd /opt/private-store/backend
id storeapp >/dev/null 2>&1 || useradd --system --home /opt/private-store --shell /usr/sbin/nologin storeapp
/opt/store-python/bin/python3.12 -m venv /opt/private-store/venv
/opt/private-store/venv/bin/pip install -i https://mirrors.aliyun.com/pypi/simple/ fastapi 'uvicorn[standard]' sqlalchemy pymysql cryptography pydantic pydantic-settings 'redis>=5.2,<6' PyJWT bcrypt httpx 'APScheduler>=3.10,<4' python-multipart pytest > /tmp/store-pip.log 2>&1
mkdir -p data
/opt/private-store/venv/bin/python - <<'PY'
import secrets
from pathlib import Path
env = Path('.env')
if not env.exists():
    env.write_text('DATABASE_URL=sqlite:////opt/private-store/backend/data/store.db\nREDIS_URL=redis://127.0.0.1:6379/1\nJWT_SECRET=' + secrets.token_hex(32) + '\nAGENT_MODE=fallback\n', encoding='utf-8')
    env.chmod(0o600)
from app.main import init_db
from app.db.session import SessionLocal
from app.seed import seed_if_empty, upgrade_demo
from app.models.tables import User
from app.core.security import hash_password
from sqlalchemy import select
credentials = Path('/root/private-store-accounts.txt')
with SessionLocal() as db:
    init_db()
    seed_if_empty(db)
    upgrade_demo(db)
    if not credentials.exists():
        rows = []
        for user in db.scalars(select(User)).all():
            password = secrets.token_urlsafe(15)
            user.password_hash = hash_password(password)
            rows.append(f'{user.username}: {password}')
        db.commit()
        credentials.write_text('\n'.join(rows) + '\n', encoding='utf-8')
        credentials.chmod(0o600)
PY
chown -R storeapp:storeapp /opt/private-store
cat > /etc/systemd/system/private-store.service <<'UNIT'
[Unit]
Description=Private store demo
After=network.target redis-server.service
[Service]
User=storeapp
Group=storeapp
WorkingDirectory=/opt/private-store/backend
ExecStart=/opt/private-store/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001 --proxy-headers
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
UMask=0077
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/nginx/sites-available/private-store <<'NGINX'
server {
    listen 127.0.0.1:8081;
    server_name kkzzzq.com www.kkzzzq.com;
    client_max_body_size 10m;
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX
ln -sfn /etc/nginx/sites-available/private-store /etc/nginx/sites-enabled/private-store
nginx -t
systemctl daemon-reload
systemctl enable --now private-store redis-server
systemctl reload nginx
