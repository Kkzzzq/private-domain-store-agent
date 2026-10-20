"""Prepare an isolated server MySQL database, without switching the running app."""
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

os.umask(0o077)
stage = Path('/opt/private-store-migration-20261020')
if stage.exists():
    raise RuntimeError('Migration staging directory already exists; inspect before retrying')
stage.mkdir()
subprocess.run(['tar', '-xzf', '/root/server-source-20261020.tar.gz', '-C', str(stage)], check=True)
backup = Path('/root/private-store-backups') / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-before-mysql')
backup.mkdir(parents=True)
shutil.copy2('/opt/private-store/backend/.env', backup / 'backend.env')
source = sqlite3.connect('file:/opt/private-store/backend/data/store.db?mode=ro', uri=True)
target = sqlite3.connect(backup / 'store.db')
source.backup(target)
assert target.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
target.close()
source.close()
subprocess.run(['tar', '-czf', str(backup / 'code-and-uploads.tar.gz'), '-C', '/opt/private-store',
                'backend/app', 'backend/knowledge', 'web'], check=True)

database = 'private_store_' + datetime.now().strftime('%Y%m%d_%H%M%S')
password = secrets.token_hex(24)
admin = create_engine('mysql+pymysql://root@localhost/mysql?unix_socket=/var/run/mysqld/mysqld.sock')
with admin.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
    conn.execute(text(f'CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
    conn.execute(text("CREATE USER IF NOT EXISTS 'store_prod'@'127.0.0.1' IDENTIFIED BY :password"), {'password': password})
    conn.execute(text("ALTER USER 'store_prod'@'127.0.0.1' IDENTIFIED BY :password"), {'password': password})
    conn.execute(text(f"GRANT ALL ON `{database}`.* TO 'store_prod'@'127.0.0.1'"))
url = URL.create('mysql+pymysql', username='store_prod', password=password, host='127.0.0.1',
                 port=3306, database=database, query={'charset': 'utf8mb4'}).render_as_string(hide_password=False)
(stage / 'backend/.env').write_text('DATABASE_URL=' + url + '\n')
subprocess.run(['/opt/private-store/venv/bin/python', '-m', 'scripts.transfer_database', 'import',
                '/root/migration-20261020.json', '--preserve-passwords', str(backup / 'store.db')],
               cwd=stage / 'backend', check=True)
state = {'stage': str(stage), 'backup': str(backup), 'database': database}
Path('/root/private-store-migration-state.json').write_text(json.dumps(state))
print(json.dumps(state))
