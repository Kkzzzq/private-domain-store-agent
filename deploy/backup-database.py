"""Root-only database backup used by the deployment receiver."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from sqlalchemy.engine import make_url

folder = Path(sys.argv[1])
folder.mkdir(parents=True, exist_ok=True)
os.chmod(folder, 0o700)
env = Path('/opt/private-store/backend/.env').read_text()
url = next(line.partition('=')[2].strip().strip('\"\'') for line in env.splitlines()
           if line.startswith('DATABASE_URL='))
parsed = make_url(url)
if parsed.drivername.startswith('sqlite'):
    source = sqlite3.connect(f'file:{parsed.database}?mode=ro', uri=True)
    target = sqlite3.connect(folder / 'store.db')
    source.backup(target)
    assert target.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    target.close()
    source.close()
elif parsed.drivername.startswith('mysql'):
    if parsed.host not in ('127.0.0.1', 'localhost'):
        raise RuntimeError('Backup is only configured for local MySQL')
    with (folder / 'mysql.sql').open('wb') as output:
        subprocess.run(['mysqldump', '--protocol=socket', '--user=root', '--single-transaction',
                        '--no-tablespaces', '--routines', '--triggers', '--events',
                        '--set-gtid-purged=OFF', '--databases', parsed.database],
                       stdout=output, check=True)
else:
    raise RuntimeError('Unsupported database backend')
print('Database backup completed:', folder)
