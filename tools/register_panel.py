#!/usr/bin/env python3
"""Merge verified domain into Olamidepanel's existing hosted-domains snapshot."""
import argparse,fcntl,grp,json,os,re,tempfile,time
from pathlib import Path

def merge(status_file,panel_data):
    if not panel_data.is_dir():return 'SKIPPED: Olamidepanel data directory not present'
    try:gid=grp.getgrnam('olamidepanel').gr_gid
    except KeyError:return 'SKIPPED: Olamidepanel runtime group not present'
    status=json.loads(status_file.read_text());domain=status['domain']
    if domain!='afribulkhub.com' or status.get('https_verified') is not True:raise ValueError('Expected a verified afribulkhub.com deployment')
    port=int(status['port'])
    if not 1024<port<65536:raise ValueError('Invalid backend port')
    target=panel_data/'hosted-domains.json';lock=panel_data/'hosted-domains.lock'
    with lock.open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX)
        previous=json.loads(target.read_text()) if target.exists() else {'domains':[]}
        if not isinstance(previous,dict) or not isinstance(previous.get('domains'),list):raise ValueError('Existing panel snapshot is malformed; refusing to replace it')
        rows=previous['domains'];old=next((r for r in rows if r.get('domain')==domain),{})
        stamp=int(time.time());row=dict(old,domain=domain,name='Africa Bulk Hub',repo='olamidebello/afribulkhub.com',service='afribulkhub',port=port,backend='http://127.0.0.1:'+str(port),health='/api/health',status='https_ready',application_ready=True,deployment_status='running',checked_at=stamp,deployment_checked_at=stamp,website='https://afribulkhub.com/',download_url='https://afribulkhub.com/downloads/africa-bulk-hub.apk')
        rows=[row if r.get('domain')==domain else r for r in rows]
        if not old:rows.append(row)
        previous.update(updated_at=stamp,domains=rows)
        fd,name=tempfile.mkstemp(prefix='.hosted-domains-',dir=panel_data)
        try:
            with os.fdopen(fd,'w') as output:json.dump(previous,output,indent=2);output.write('\n');output.flush();os.fsync(output.fileno())
            os.chmod(name,0o640);os.chown(name,0,gid);os.replace(name,target)
        finally:Path(name).unlink(missing_ok=True)
    return 'UPDATED: afribulkhub.com registered in Hosting Domains snapshot'
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--status',type=Path,default=Path('/var/lib/afribulkhub/hosting-status.json'));p.add_argument('--panel-data',type=Path,default=Path('/var/lib/olamidepanel'));a=p.parse_args();print(merge(a.status,a.panel_data))
