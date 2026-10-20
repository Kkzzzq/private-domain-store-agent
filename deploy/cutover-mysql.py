"""Switch the prepared snapshot and code together, with automatic rollback."""
import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

state = json.loads(Path('/root/private-store-migration-state.json').read_text())
stage, backup = Path(state['stage']), Path(state['backup'])
app = Path('/opt/private-store')
new_url_line = (stage / 'backend/.env').read_text().strip()
old_env = (app / 'backend/.env').read_text()
new_env = '\n'.join(new_url_line if line.startswith('DATABASE_URL=') else line
                    for line in old_env.splitlines()) + '\n'
# A fresh Redis namespace avoids cached data and chat context from the old database.
new_env = '\n'.join('REDIS_URL=redis://127.0.0.1:6379/2' if line.startswith('REDIS_URL=') else line
                    for line in new_env.splitlines()) + '\n'
subprocess.run(['systemctl', 'stop', 'private-store'], check=True)
try:
    # Snapshot the final pre-cutover state while writes are stopped.
    subprocess.run([str(app / 'venv/bin/python'), '/usr/local/sbin/private-store-backup-db',
                    str(backup / 'final')], check=True)
    for directory in ('backend/app', 'backend/knowledge'):
        subprocess.run(['rsync', '-a', '--delete', str(stage / directory) + '/', str(app / directory) + '/'], check=True)
    subprocess.run(['rsync', '-a', '--delete', '--exclude=covers/uploads/', str(stage / 'web') + '/', str(app / 'web') + '/'], check=True)
    uploads = stage / 'web/covers/uploads'
    if uploads.exists():
        subprocess.run(['rsync', '-a', str(uploads) + '/', str(app / 'web/covers/uploads') + '/'], check=True)
    (app / 'backend/.env').write_text(new_env)
    subprocess.run(['chown', '-R', 'storeapp:storeapp', str(app / 'backend/app'), str(app / 'backend/knowledge'),
                    str(app / 'web'), str(app / 'backend/.env')], check=True)
    subprocess.run(['systemctl', 'start', 'private-store'], check=True)
    for attempt in range(45):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8001/api/v1/ready', timeout=3) as response:
                ready = json.load(response)
            if ready['status'] == 'ready' and ready['database'] == 'mysql' and ready['redis'] == 'redis':
                break
        except Exception:
            pass
        time.sleep(2)
    else:
        raise RuntimeError('MySQL readiness check failed')
    subprocess.run([str(app / 'venv/bin/python'), '/usr/local/sbin/private-store-backup-db', str(backup / 'mysql-initial')], check=True)
    print(json.dumps({'status': 'ready', 'database': state['database'], 'backup': str(backup)}))
except Exception:
    subprocess.run(['systemctl', 'stop', 'private-store'])
    rollback = backup / 'rollback'
    rollback.mkdir(exist_ok=True)
    subprocess.run(['tar', '-xzf', str(backup / 'code-and-uploads.tar.gz'), '-C', str(rollback)], check=True)
    for directory in ('backend/app', 'backend/knowledge', 'web'):
        subprocess.run(['rsync', '-a', '--delete', str(rollback / directory) + '/', str(app / directory) + '/'], check=True)
    (app / 'backend/.env').write_text(old_env)
    subprocess.run(['chown', '-R', 'storeapp:storeapp', str(app / 'backend/app'), str(app / 'backend/knowledge'),
                    str(app / 'web'), str(app / 'backend/.env')])
    subprocess.run(['systemctl', 'start', 'private-store'])
    raise
