"""Add the shop hostname while leaving the primary-domain configuration intact."""
import hashlib
import subprocess
import sys
from pathlib import Path
from datetime import datetime

tls = sys.argv[1:] == ['https']
primary = Path('/etc/nginx/sites-available/private-store')
primary_hash = hashlib.sha256(primary.read_bytes()).hexdigest()
config = Path('/etc/nginx/sites-available/private-store-shop')
backup = Path('/root/private-store-backups') / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-shop-domain')
backup.mkdir(parents=True)
if config.exists():
    (backup / 'private-store-shop.conf').write_bytes(config.read_bytes())
http = '''server {
    listen 80;
    server_name shop.kkzzzq.cyou;
    location ^~ /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { REPLACE_LOCATION }
}
'''
proxy = '''proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 300s;'''
if tls:
    content = http.replace('REPLACE_LOCATION', 'return 301 https://shop.kkzzzq.cyou$request_uri;')
    content += '''server {
    listen 443 ssl;
    server_name shop.kkzzzq.cyou;
    ssl_certificate /etc/letsencrypt/live/shop.kkzzzq.cyou/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/shop.kkzzzq.cyou/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 10m;
    location / { REPLACE_PROXY }
}
'''.replace('REPLACE_PROXY', proxy)
else:
    content = http.replace('REPLACE_LOCATION', proxy)
config.write_text(content)
enabled = Path('/etc/nginx/sites-enabled/private-store-shop')
if not enabled.exists():
    enabled.symlink_to(config)
subprocess.run(['nginx', '-t'], check=True)
subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
assert hashlib.sha256(primary.read_bytes()).hexdigest() == primary_hash
print('Shop hostname configured; primary config unchanged; TLS:', tls)
