#!/usr/bin/env python3
"""Provision one initial admin; keep generated credentials root-only, never in logs."""
import argparse,json,os,re,secrets,subprocess
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--email',required=True);p.add_argument('--install',default='/opt/afribulkhub');p.add_argument('--database',default='/var/lib/afribulkhub/hub.db');a=p.parse_args()
    if os.geteuid()!=0:raise SystemExit('Run initial administrator provisioning as root')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',a.email):raise SystemExit('Valid administrator email required')
    env=dict(os.environ,ABH_DATABASE=a.database);python=str(Path(a.install)/'venv/bin/python');script=str(Path(a.install)/'app.py')
    check='import sqlite3,os,json; c=sqlite3.connect(os.environ["ABH_DATABASE"]); print(json.dumps([c.execute("SELECT COUNT(*) FROM users WHERE role=?",("super_admin",)).fetchone()[0],c.execute("SELECT COUNT(*) FROM users WHERE email=?",(os.environ["ABH_BOOTSTRAP_EMAIL"],)).fetchone()[0]]))'
    env['ABH_BOOTSTRAP_EMAIL']=a.email.lower()
    counts=json.loads(subprocess.check_output(['runuser','-u','afribulkhub','--',python,'-c',check],env=env,text=True))
    if counts[0]:print('UNCHANGED: Existing super administrator preserved');return
    if counts[1]:raise SystemExit('Administrator email is already a regular account. Review it explicitly; no automatic privilege elevation performed.')
    state=Path('/var/lib/afribulkhub-bootstrap');state.mkdir(mode=0o700,exist_ok=True)
    credentials=state/'initial-admin.json'
    if credentials.exists():
        saved=json.loads(credentials.read_text())
        if saved.get('email')!=a.email.lower():raise SystemExit('Existing bootstrap credential email differs; inspect it before continuing')
        password=saved['password']
    else:
        password=secrets.token_urlsafe(24);fd=os.open(credentials,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as output:json.dump({'email':a.email.lower(),'password':password,'website':'https://afribulkhub.com/'},output)
    env['ABH_ADMIN_PASSWORD']=password
    subprocess.run(['runuser','-u','afribulkhub','--',python,script,'admin','--email',a.email.lower()],env=env,check=True,capture_output=True,text=True)
    print('CREATED: Initial administrator; credentials in /var/lib/afribulkhub-bootstrap/initial-admin.json (root only)')
if __name__=='__main__':main()
