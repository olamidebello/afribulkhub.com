#!/usr/bin/env python3
"""Select a free loopback port without stopping or taking over another service."""
import argparse,json,re,socket,urllib.request
from pathlib import Path

def available(port):
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        try:sock.bind(('127.0.0.1',port));return True
        except OSError:return False

def owned(port):
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:'+str(port)+'/api/health',timeout=1) as r:
            return r.status==200 and json.load(r).get('service')=='afribulkhub'
    except Exception:return False

def choose(preferred=0,saved=None,vhost=None,domain='afribulkhub.com',start=18770,end=18869):
    prior=[]
    if saved and saved.exists():
        value=json.loads(saved.read_text())['port']
        if type(value)!=int or not 1024<value<65536:raise ValueError('Invalid saved port configuration')
        prior.append(value)
    if vhost and vhost.exists():
        content=vhost.read_text()
        names=[name for group in re.findall(r'\bserver_name\s+([^;]+);',content) for name in group.split()]
        if domain not in names:raise ValueError('Dedicated vhost belongs to a different domain; refusing to alter it')
        ports=set(map(int,re.findall(r'\bproxy_pass\s+http://127\.0\.0\.1:(\d+)\s*;',content)))
        if len(ports)!=1:raise ValueError('Expected one dedicated loopback backend; inspect the existing vhost')
        prior.extend(ports)
    if preferred:
        if not 1024<preferred<65536:raise ValueError('Port must be 1025–65535, or 0 for automatic selection')
        if available(preferred) or owned(preferred):return preferred
        raise ValueError('Requested port '+str(preferred)+' belongs to another service. Use hub_port=0 for automatic selection.')
    for port in dict.fromkeys(prior):
        if available(port) or owned(port):return port
    for port in range(start,end+1):
        if available(port) or owned(port):return port
    raise ValueError('No free Africa Bulk Hub port found in '+str(start)+'–'+str(end))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--preferred',type=int,default=0);p.add_argument('--saved',type=Path);p.add_argument('--vhost',type=Path);p.add_argument('--domain',default='afribulkhub.com');a=p.parse_args()
    print(json.dumps({'port':choose(a.preferred,a.saved,a.vhost,a.domain)}))
