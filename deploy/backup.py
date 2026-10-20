"""Consistent on-server backup. Replicate to encrypted off-server storage separately."""
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
base=Path(os.environ.get('ABH_DATA','/var/lib/afribulkhub'))
out=base/'backups';out.mkdir(mode=0o700,exist_ok=True)
path=out/(datetime.now(timezone.utc).strftime('hub-%Y%m%dT%H%M%SZ')+'.db')
os.umask(0o077)
with sqlite3.connect(base/'hub.db') as source,sqlite3.connect(path) as target:
    source.backup(target)
    assert target.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
print(path)
