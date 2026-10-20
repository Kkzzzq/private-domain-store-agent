"""Run as root on the existing server after issuing the domain certificate."""
from datetime import datetime
from pathlib import Path
import shutil
import subprocess

root = Path('/opt/private-store')
backup = Path('/root/private-store-backups') / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-domain')
backup.mkdir(parents=True)
config = Path('/etc/nginx/sites-available/private-store')
shutil.copy2(config, backup / 'nginx.conf')
for name in ('index.html', 'c.html', 'b.html'):
    path = root / 'web' / name
    shutil.copy2(path, backup / name)
    text = path.read_text()
    if '/site-registration.js' not in text:
        path.write_text(text.replace('</body>', '  <script src="/site-registration.js?v=20261020"></script>\n</body>'))

config.write_text('''server {
    listen 80;
    server_name kkzzzq.cyou;
    location ^~ /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 301 https://kkzzzq.cyou$request_uri; }
}
server {
    listen 443 ssl;
    listen 127.0.0.1:8081;
    server_name kkzzzq.cyou;
    ssl_certificate /etc/letsencrypt/live/kkzzzq.cyou/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/kkzzzq.cyou/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 10m;
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
}
''')
try:
    subprocess.run(['nginx', '-t'], check=True)
    subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
except Exception:
    shutil.copy2(backup / 'nginx.conf', config)
    raise
hook = Path('/etc/letsencrypt/renewal-hooks/deploy/reload-nginx')
hook.parent.mkdir(parents=True, exist_ok=True)
hook.write_text('#!/bin/sh\nnginx -t && systemctl reload nginx\n')
hook.chmod(0o755)
subprocess.run(['systemctl', 'enable', '--now', 'certbot.timer'], check=True)
print('Domain configured; backup:', backup)
