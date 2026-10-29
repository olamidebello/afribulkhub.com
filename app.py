"""Africa Bulk Hub. WSGI application; durable SQLite, explicit access checks."""
import argparse
import alibaba_import
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
import base64
import hashlib
import hmac
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

ROOT = Path(__file__).parent
DB = os.environ.get('ABH_DATABASE', str(ROOT / 'data' / 'hub.db'))
SECURE = os.environ.get('ABH_SECURE_COOKIE', '1') == '1'

SCHEMA = '''
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS tenants(id INTEGER PRIMARY KEY,name TEXT NOT NULL,country TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'active',created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL REFERENCES tenants(id),name TEXT NOT NULL,email TEXT NOT NULL UNIQUE,password TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('buyer','supplier','provider','tenant_admin','super_admin')),status TEXT NOT NULL DEFAULT 'active',created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS acceptances(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),terms_version TEXT NOT NULL,privacy_version TEXT NOT NULL,created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS user_languages(user_id INTEGER PRIMARY KEY REFERENCES users(id),language TEXT NOT NULL DEFAULT 'pcm');
CREATE TABLE IF NOT EXISTS schema_migrations(name TEXT PRIMARY KEY,created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS user_currencies(user_id INTEGER PRIMARY KEY REFERENCES users(id),currency TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),csrf TEXT NOT NULL,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,tenant_id INTEGER NOT NULL REFERENCES tenants(id),owner_id INTEGER NOT NULL REFERENCES users(id),peer_tenant INTEGER REFERENCES tenants(id),status TEXT NOT NULL,data TEXT NOT NULL,created INTEGER NOT NULL,updated INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS record_kind ON records(kind,tenant_id);
CREATE TABLE IF NOT EXISTS cart(user_id INTEGER NOT NULL REFERENCES users(id),product_id INTEGER NOT NULL REFERENCES records(id),quantity INTEGER NOT NULL,PRIMARY KEY(user_id,product_id));
CREATE TABLE IF NOT EXISTS attachments(id INTEGER PRIMARY KEY,record_id INTEGER NOT NULL REFERENCES records(id),uploader_id INTEGER NOT NULL REFERENCES users(id),filename TEXT NOT NULL,mime TEXT NOT NULL,content BLOB NOT NULL,created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS favorites(user_id INTEGER REFERENCES users(id),record_id INTEGER REFERENCES records(id),PRIMARY KEY(user_id,record_id));
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,actor_id INTEGER,tenant_id INTEGER,action TEXT NOT NULL,record_id INTEGER,created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,count INTEGER NOT NULL,start INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS resets(token TEXT PRIMARY KEY,user_id INTEGER NOT NULL,expires INTEGER NOT NULL);
'''
KINDS = {'product','rfq','quote','order','job','application','message','ticket','dispute','review','verification','campaign','notification','address'}
PUBLIC = {'product','rfq','job'}
DEFAULTS = {'platform_name':'Africa Bulk Hub','commission_percent':5,'seller_monthly_usd':29,'support_email':'','countries':['Nigeria','Ghana','Kenya','South Africa','Egypt','United States'],'currencies':[r['code'] for r in json.loads((ROOT/'static/currencies.json').read_text())['currencies']],'default_currency':'NGN','payments_enabled':False,'registration_enabled':True}

def connect():
    p = Path(DB); p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=20); c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init_db():
    with connect() as c:
        c.executescript(SCHEMA)
        alibaba_import.init(c)
        c.execute("BEGIN IMMEDIATE")
        for k,v in DEFAULTS.items():
            c.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',(k,json.dumps(v)))
        existing_codes=c.execute('SELECT value FROM settings WHERE key=?',('currencies',)).fetchone()
        if json.loads(existing_codes[0])!=DEFAULTS['currencies']:
            c.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps(DEFAULTS['currencies']),'currencies'))
        if not c.execute("SELECT 1 FROM schema_migrations WHERE name='currencies-v1'").fetchone():
            # Earlier releases priced all monetary records in USD. Preserve the unit,
            # including products and quotations which did not store a currency field.
            for row in c.execute("SELECT id,kind,data FROM records WHERE kind IN ('product','rfq','job','quote','application','order','dispute','campaign')").fetchall():
                data=json.loads(row['data'])
                if not data.get('currency'):
                    data['currency']='USD';c.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(data),row['id']))
            c.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps(DEFAULTS['currencies']),'currencies'))
            c.execute('INSERT INTO schema_migrations VALUES (?,?)',('currencies-v1',now()))


@lru_cache(maxsize=1)
def language_codes():
    data=json.loads((ROOT/'static/i18n/languages.json').read_text())
    return frozenset(item['code'] for item in data['languages'])

@lru_cache(maxsize=1)
def currency_info():
    return {r['code']:r for r in json.loads((ROOT/'static/currencies.json').read_text())['currencies']}

def currency_code(value=None):
    code=str(value or 'NGN').strip().upper()
    require(code in currency_info(),'Unsupported currency',400)
    return code

def monetary(d,key,code,minimum=0):
    value=number(d,key,minimum);unit=Decimal(1).scaleb(-currency_info()[code]['minor_units']);decimal=Decimal(str(value))
    require(decimal==decimal.quantize(unit),'Too many decimal places for '+code,400)
    return value

def total_price(price,quantity,code):
    unit=Decimal(1).scaleb(-currency_info()[code]['minor_units'])
    return float((Decimal(str(price))*Decimal(str(quantity))).quantize(unit,rounding=ROUND_HALF_UP))

def password_hash(p):
    salt = secrets.token_hex(16)
    return salt + ':' + hashlib.scrypt(p.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()

def password_ok(p, stored):
    salt, val = stored.split(':')
    return hmac.compare_digest(val,hashlib.scrypt(p.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex())

class Error(Exception):
    def __init__(self, status, message): self.status, self.message = status, message

def require(ok, message='Permission denied', status=403):
    if not ok: raise Error(status,message)

def clean(v, limit=500): return str(v or '').strip()[:limit]
def now(): return int(time.time())
def settings(c): return {r['key']:json.loads(r['value']) for r in c.execute('SELECT * FROM settings')}
def audit(c,u,action,rid=None):
    c.execute('INSERT INTO audit(actor_id,tenant_id,action,record_id,created) VALUES (?,?,?,?,?)',(u['id'] if u else None,u['tenant_id'] if u else None,action,rid,now()))
def person(c,uid):
    r=c.execute('SELECT u.id,u.tenant_id,u.name,u.email,u.role,u.status,t.name company,t.country FROM users u JOIN tenants t ON t.id=u.tenant_id WHERE u.id=?',(uid,)).fetchone()
    if not r:return None
    result=dict(r);preference=c.execute('SELECT language FROM user_languages WHERE user_id=?',(uid,)).fetchone()
    result['language']=preference[0] if preference else None
    currency=c.execute('SELECT currency FROM user_currencies WHERE user_id=?',(uid,)).fetchone();result['currency']=currency[0] if currency else None
    return result

def visible(u,r):
    return (r['kind'] in PUBLIC and r['status']=='published') or (u and (u['role']=='super_admin' or u['tenant_id'] in (r['tenant_id'],r['peer_tenant'])))
def record(c,rid):
    r=c.execute('SELECT * FROM records WHERE id=?',(rid,)).fetchone()
    require(r is not None,'Not found',404)
    return r

def output(c,r):
    d=dict(r); d['data']=json.loads(d['data'])
    d['company']=c.execute('SELECT name FROM tenants WHERE id=?',(r['tenant_id'],)).fetchone()[0]
    return d

def add(c,u,kind,data,status='open',peer=None):
    cur=c.execute('INSERT INTO records(kind,tenant_id,owner_id,peer_tenant,status,data,created,updated) VALUES (?,?,?,?,?,?,?,?)',(kind,u['tenant_id'],u['id'],peer,status,json.dumps(data),now(),now()))
    audit(c,u,'create:'+kind,cur.lastrowid)
    return output(c,record(c,cur.lastrowid))

def number(d,key,minimum=0):
    try: v=float(d.get(key,0))
    except (TypeError,ValueError): raise Error(400,'Invalid '+key)
    require(v>=minimum and v<1e12 and v==v,'Invalid '+key,400)
    return v

def sanitize(kind,d):
    allowed={
      'product':['title','description','category','country','price','moq','stock','unit','lead_time','variants','certifications','customization'],
      'rfq':['title','description','category','quantity','destination','budget','deadline'],
      'job':['title','description','category','location','budget','deadline','skills'],
      'ticket':['title','description','priority'], 'dispute':['title','description','order_id','amount'],
      'verification':['title','description','registration_number'], 'campaign':['title','description','budget'],
      'address':['title','description','country','city','postal_code'],
    }.get(kind,[])
    result={k:clean(d.get(k),4000 if k=='description' else 500) for k in allowed}
    require(result.get('title'),'Title is required',400)
    if kind in {'product','rfq','job','campaign'}:result['currency']=currency_code(d.get('currency'))
    if kind=='product':
        result.update(price=monetary(d,'price',result['currency'],0.001),moq=number(d,'moq',1),stock=number(d,'stock'),unit=clean(d.get('unit') or 'unit'))
    if kind in {'rfq','job','campaign'}: result['budget']=monetary(d,'budget',result['currency'])
    if kind=='rfq': result['quantity']=number(d,'quantity',1)
    return result

def auth(c,environ):
    cookies={}
    for part in environ.get('HTTP_COOKIE','').split(';'):
        if '=' in part:
            k,v=part.strip().split('=',1); cookies[k]=v
    raw=cookies.get('abh_session','')
    s=c.execute('SELECT * FROM sessions WHERE token=? AND expires>?',(hashlib.sha256(raw.encode()).hexdigest(),now())).fetchone()
    if not s: return None,None
    u=person(c,s['user_id'])
    tenant=c.execute('SELECT status FROM tenants WHERE id=?',(u['tenant_id'],)).fetchone()
    if u['status']!='active' or tenant[0]!='active': return None,None
    return u,s

def login(c,u):
    token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32)
    c.execute('INSERT INTO sessions VALUES (?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u['id'],csrf,now()+43200))
    return {'user':u,'csrf':csrf}, [('Set-Cookie','abh_session='+token+'; Path=/; HttpOnly; SameSite=Lax; Max-Age=43200'+('; Secure' if SECURE else ''))]

def limit(c,key,maximum=15):
    r=c.execute('SELECT * FROM attempts WHERE key=?',(key,)).fetchone()
    if not r or r['start']<now()-900:
        c.execute('INSERT OR REPLACE INTO attempts VALUES (?,1,?)',(key,now()))
    else:
        require(r['count']<maximum,'Too many attempts. Try again in 15 minutes.',429)
        c.execute('UPDATE attempts SET count=count+1 WHERE key=?',(key,))

def api(c,env,method,path,d,q):
    u,s=auth(c,env); extra=[]
    if method!='GET':
        origin=env.get('HTTP_ORIGIN')
        if origin:
            from urllib.parse import urlsplit
            require(urlsplit(origin).netloc==env.get('HTTP_HOST'),'Invalid origin')
        if s: require(hmac.compare_digest(env.get('HTTP_X_CSRF_TOKEN',''),s['csrf']),'Refresh the page and try again')
    if path in {'/api/health','/api/session'}: require(method=='GET','Method not allowed',405)
    if path=='/api/health': return {'status':'ok','service':'afribulkhub'},extra
    if path=='/api/session': return {'user':u,'csrf':s['csrf'] if s else None},extra
    if path=='/api/currencies' and method=='GET':return json.loads((ROOT/'static/currencies.json').read_text()),extra
    if path=='/api/settings' and method=='GET': return settings(c),extra
    if path in {'/api/register','/api/login','/api/recover','/api/reset'}:
        require(method=='POST','Method not allowed',405)
        email=clean(d.get('email')).lower()
        if path=='/api/register':
            require(d.get('accept_terms') is True,'Agree to the Terms and acknowledge the Privacy Policy to register',400)
            require(settings(c)['registration_enabled'],'Registration is currently closed')
            require(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email),'Valid email required',400)
            require(len(d.get('password',''))>=12,'Password must have at least 12 characters',400)
            require(d.get('role') in {'buyer','supplier','provider'},'Invalid account type',400)
            require(clean(d.get('company')) and clean(d.get('name')),'Name and company are required',400)
            require(not c.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone(),'Email already registered',409)
            tid=c.execute('INSERT INTO tenants(name,country,created) VALUES (?,?,?)',(clean(d['company']),clean(d.get('country') or 'Nigeria'),now())).lastrowid
            uid=c.execute('INSERT INTO users(tenant_id,name,email,password,role,created) VALUES (?,?,?,?,?,?)',(tid,clean(d['name']),email,password_hash(d['password']),d['role'],now())).lastrowid
            c.execute('INSERT INTO acceptances(user_id,terms_version,privacy_version,created) VALUES (?,?,?,?)',(uid,'2026-10-20','2026-10-20',now()))
            audit(c,person(c,uid),'register')
            return login(c,person(c,uid))
        if path=='/api/login':
            r=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
            valid=password_ok(d.get('password',''),r['password']) if r else password_ok(d.get('password',''),password_hash('dummy-password'))
            require(r and valid,'Email or password is incorrect',401)
            require(r['status']=='active' and c.execute('SELECT status FROM tenants WHERE id=?',(r['tenant_id'],)).fetchone()[0]=='active','Account is suspended')
            return login(c,person(c,r['id']))
        if path=='/api/recover':
            # Recovery is mediated by an operator until an email provider is configured.
            return {'message':'For account recovery, contact the marketplace operator. They can issue a single-use reset code after verifying your identity.'},extra
        token=hashlib.sha256(clean(d.get('token')).encode()).hexdigest()
        r=c.execute('SELECT * FROM resets WHERE token=? AND expires>?',(token,now())).fetchone()
        require(r,'Invalid or expired reset code',400)
        require(len(d.get('password',''))>=12,'Password must have at least 12 characters',400)
        c.execute('UPDATE users SET password=? WHERE id=?',(password_hash(d['password']),r['user_id']))
        c.execute('DELETE FROM resets WHERE user_id=?',(r['user_id'],));c.execute('DELETE FROM sessions WHERE user_id=?',(r['user_id'],))
        return {'message':'Password reset. You can sign in now.'},extra
    if path=='/api/logout':
        require(method=='POST','Method not allowed',405)
        if s: c.execute('DELETE FROM sessions WHERE token=?',(s['token'],))
        return {'ok':True},[('Set-Cookie','abh_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0'+('; Secure' if SECURE else ''))]
    if path=='/api/records' and method=='GET':
        kind=q.get('kind',['product'])[0];require(kind in KINDS,'Unknown module',400)
        mine=q.get('mine',['0'])[0]=='1'
        if mine: require(u,'Sign in required',401)
        search=q.get('search',[''])[0].lower();category=q.get('category',[''])[0]
        rows=[]
        for r in c.execute('SELECT * FROM records WHERE kind=? ORDER BY id DESC LIMIT 2000',(kind,)):
            if not visible(u,r):continue
            if not (u and u['role']=='super_admin') and c.execute('SELECT status FROM tenants WHERE id=?',(r['tenant_id'],)).fetchone()[0]!='active':continue
            if mine and u['role']!='super_admin' and u['tenant_id'] not in (r['tenant_id'],r['peer_tenant']):continue
            item=output(c,r)
            if search and search not in (json.dumps(item['data'])+item['company']).lower():continue
            if category and item['data'].get('category')!=category:continue
            rows.append(item)
        return {'items':rows[:250]},extra
    m=re.fullmatch(r'/api/stores/(\d+)',path)
    if m and method=='GET':
        tid=int(m[1]);t=c.execute('SELECT id,name,country FROM tenants WHERE id=? AND status=\'active\'',(tid,)).fetchone()
        require(t,'Store not found',404)
        products=[output(c,r) for r in c.execute("SELECT * FROM records WHERE tenant_id=? AND kind='product' AND status='published'",(tid,))]
        require(products,'No public storefront yet',404)
        return {'store':dict(t),'products':products},extra
    m=re.fullmatch(r'/api/attachments/(\d+)',path)
    if m and method=='GET':
        require(u,'Sign in required',401)
        a=c.execute('SELECT * FROM attachments WHERE id=?',(int(m[1]),)).fetchone();require(a,'Not found',404)
        r=record(c,a['record_id']);require(visible(u,r),'Not found',404)
        return {'filename':a['filename'],'mime':a['mime'],'content':base64.b64encode(a['content']).decode()},extra
    if path.startswith('/api/records/') and method=='GET':
        r=record(c,int(path.rsplit('/',1)[-1]));require(visible(u,r),'Not found',404)
        return output(c,r),extra
    require(u,'Sign in required',401)
    if path=='/api/attachments':
        rid=int(q.get('record_id',[0])[0] if method=='GET' else d.get('record_id',0));r=record(c,rid)
        require(visible(u,r),'Not found',404)
        if method=='GET':
            return {'items':[dict(a) for a in c.execute('SELECT id,filename,mime,created FROM attachments WHERE record_id=?',(rid,))]},extra
        require(method=='POST','Method not allowed',405)
        require(u['role']=='super_admin' or u['tenant_id'] in (r['tenant_id'],r['peer_tenant']),'Cannot attach to this record')
        require(c.execute('SELECT COUNT(*) FROM attachments WHERE record_id=?',(rid,)).fetchone()[0]<10,'Maximum ten attachments per record',400)
        try: blob=base64.b64decode(d.get('content',''),validate=True)
        except (ValueError,TypeError):raise Error(400,'Invalid file encoding')
        require(0<len(blob)<=2*1024*1024,'Maximum attachment size is 2 MiB',400)
        filename=Path(clean(d.get('filename'),150)).name
        require(filename,'Filename required',400)
        mime='application/pdf' if blob.startswith(b'%PDF-') else ('image/png' if blob.startswith(b'\x89PNG\r\n\x1a\n') else ('image/jpeg' if blob.startswith(b'\xff\xd8\xff') else None))
        require(mime,'Only PDF, PNG and JPEG files are accepted',400)
        aid=c.execute('INSERT INTO attachments(record_id,uploader_id,filename,mime,content,created) VALUES (?,?,?,?,?,?)',(rid,u['id'],filename,mime,blob,now())).lastrowid
        audit(c,u,'attachment:upload',rid);return {'id':aid,'filename':filename},extra
    if path=='/api/cart':
        if method=='GET':
            items=[]
            for item in c.execute('SELECT product_id,quantity FROM cart WHERE user_id=?',(u['id'],)):
                r=record(c,item['product_id'])
                if visible(u,r):
                    o=output(c,r);o['quantity']=item['quantity'];items.append(o)
            return {'items':items},extra
        require(method in {'POST','DELETE'},'Method not allowed',405)
        pid=int(d.get('product_id',0))
        if method=='DELETE':
            c.execute('DELETE FROM cart WHERE user_id=? AND product_id=?',(u['id'],pid));return {'ok':True},extra
        r=record(c,pid);require(r['kind']=='product' and r['status']=='published','Product unavailable',400)
        require(r['tenant_id']!=u['tenant_id'],'Cannot order your own product',400)
        pd=json.loads(r['data']);qty=number(d,'quantity',pd['moq']);require(qty.is_integer() and qty<=pd['stock'],'Invalid quantity or insufficient stock',400)
        c.execute('INSERT INTO cart VALUES (?,?,?) ON CONFLICT(user_id,product_id) DO UPDATE SET quantity=excluded.quantity',(u['id'],pid,int(qty)))
        return {'ok':True},extra
    if path=='/api/checkout' and method=='POST':
        address=clean(d.get('delivery_address'),1500);require(address,'Delivery address required',400)
        items=c.execute('SELECT * FROM cart WHERE user_id=?',(u['id'],)).fetchall();require(items,'Cart is empty',400)
        orders=[]
        for item in items:
            p=record(c,item['product_id']);require(c.execute('SELECT status FROM tenants WHERE id=?',(p['tenant_id'],)).fetchone()[0]=='active','Supplier is unavailable',409);require(p['status']=='published','A cart item is no longer available',409)
            alibaba_import.fresh(c,p['id'],__import__(__name__))
            pd=json.loads(p['data']);qty=item['quantity'];require(pd['moq']<=qty<=pd['stock'],'Stock or MOQ has changed. Update your cart.',409)
            pd['stock']-=qty;c.execute('UPDATE records SET data=?,updated=? WHERE id=?',(json.dumps(pd),now(),p['id']))
            orders.append(add(c,u,'order',{'product_id':p['id'],'title':pd['title'],'quantity':qty,'unit_price':pd['price'],'total':total_price(pd['price'],qty,pd['currency']),'currency':pd['currency'],'delivery_address':address,'payment_status':'unpaid','stock_reserved':True},'pending',p['tenant_id']))
        c.execute('DELETE FROM cart WHERE user_id=?',(u['id'],));return {'items':orders},extra
    if path=='/api/language':
        if method=='GET':return {'language':u.get('language') or 'pcm','default':'pcm'},extra
        require(method=='PATCH','Method not allowed',405)
        code=clean(d.get('language'),50);require(code in language_codes(),'Unknown language code',400)
        c.execute('INSERT INTO user_languages VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET language=excluded.language',(u['id'],code))
        audit(c,u,'language:update');return {'language':code,'default':'pcm'},extra
    if path=='/api/currency':
        if method=='GET':return {'currency':u.get('currency') or 'NGN','default':'NGN'},extra
        require(method=='PATCH','Method not allowed',405);code=currency_code(d.get('currency'))
        c.execute('INSERT INTO user_currencies VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET currency=excluded.currency',(u['id'],code))
        audit(c,u,'currency:update');return {'currency':code,'default':'NGN'},extra
    if path=='/api/profile' and method=='PATCH':
        require(clean(d.get('name')),'Name required',400)
        c.execute('UPDATE users SET name=? WHERE id=?',(clean(d['name']),u['id']))
        # Only tenant admins (or sole founding account) may change the company name.
        if d.get('company') and (u['role'] in {'tenant_admin','super_admin'} or c.execute('SELECT COUNT(*) FROM users WHERE tenant_id=?',(u['tenant_id'],)).fetchone()[0]==1):
            c.execute('UPDATE tenants SET name=?,country=? WHERE id=?',(clean(d['company']),clean(d.get('country')),u['tenant_id']))
        audit(c,u,'profile:update');return person(c,u['id']),extra
    if path=='/api/password' and method=='POST':
        r=c.execute('SELECT password FROM users WHERE id=?',(u['id'],)).fetchone()
        require(password_ok(d.get('current',''),r[0]),'Current password is incorrect',400)
        require(len(d.get('password',''))>=12,'Password must have at least 12 characters',400)
        c.execute('UPDATE users SET password=? WHERE id=?',(password_hash(d['password']),u['id']))
        c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],));audit(c,u,'password:change')
        return {'message':'Password updated. Sign in again.'},extra
    if path=='/api/favorites':
        if method=='GET':
            rows=[output(c,r) for r in c.execute('SELECT r.* FROM records r JOIN favorites f ON f.record_id=r.id WHERE f.user_id=?',(u['id'],)) if visible(u,r)]
            return {'items':rows},extra
        require(method=='POST','Method not allowed',405)
        r=record(c,int(d.get('record_id',0)));require(visible(u,r),'Not found',404)
        if c.execute('SELECT 1 FROM favorites WHERE user_id=? AND record_id=?',(u['id'],r['id'])).fetchone():c.execute('DELETE FROM favorites WHERE user_id=? AND record_id=?',(u['id'],r['id']))
        else:c.execute('INSERT INTO favorites VALUES (?,?)',(u['id'],r['id']))
        return {'ok':True},extra
    if path=='/api/records' and method=='POST':
        kind=d.get('kind');require(kind in KINDS,'Unknown module',400)
        data=d.get('data',{});require(isinstance(data,dict),'Expected record fields object',400);peer=None
        data=dict(data)
        if kind in {'product','rfq','job','campaign','quote','application'}:data.setdefault('currency',u.get('currency') or 'NGN')
        if kind in {'product','campaign'}:require(u['role'] in {'supplier','tenant_admin','super_admin'},'Supplier account required')
        if kind in {'product','rfq','job','ticket','verification','campaign','address'}:
            return add(c,u,kind,sanitize(kind,data),'pending' if kind in {'product','verification','campaign'} else ('published' if kind in {'rfq','job'} else 'open')),extra
        if kind=='quote':
            require(u['role'] in {'supplier','tenant_admin','super_admin'},'Supplier account required')
            target=record(c,int(data.get('rfq_id',0)));require(target['kind']=='rfq' and target['status']=='published','RFQ is closed',400)
            require(target['tenant_id']!=u['tenant_id'],'Cannot quote your own request',400)
            return add(c,u,kind,{'rfq_id':target['id'],'title':json.loads(target['data'])['title'],'price':monetary(data,'price',currency_code(data.get('currency')),0.001),'currency':currency_code(data.get('currency')),'quantity':number(data,'quantity',1),'lead_time':clean(data.get('lead_time')),'description':clean(data.get('description'),4000)},peer=target['tenant_id']),extra
        if kind=='order':
            target=record(c,int(data.get('product_id',0)));require(c.execute('SELECT status FROM tenants WHERE id=?',(target['tenant_id'],)).fetchone()[0]=='active','Supplier is unavailable',409);require(target['kind']=='product' and target['status']=='published','Product unavailable',400)
            require(target['tenant_id']!=u['tenant_id'],'Cannot order your own product',400)
            alibaba_import.fresh(c,target['id'],__import__(__name__))
            p=json.loads(target['data']);qty=number(data,'quantity',p['moq']);require(qty.is_integer(),'Quantity must be a whole number',400)
            require(qty<=float(p['stock']),'Requested quantity exceeds available stock',400)
            p['stock']=float(p['stock'])-qty;c.execute('UPDATE records SET data=?,updated=? WHERE id=?',(json.dumps(p),now(),target['id']))
            return add(c,u,kind,{'product_id':target['id'],'title':p['title'],'quantity':qty,'unit_price':p['price'],'total':total_price(p['price'],qty,p['currency']),'currency':p['currency'],'delivery_address':clean(data.get('delivery_address'),1500),'payment_status':'unpaid','stock_reserved':True},'pending',target['tenant_id']),extra
        if kind=='application':
            target=record(c,int(data.get('job_id',0)));require(target['kind']=='job' and target['status']=='published','Job unavailable',400)
            require(target['tenant_id']!=u['tenant_id'],'Cannot apply to your own job',400)
            return add(c,u,kind,{'job_id':target['id'],'title':json.loads(target['data'])['title'],'price':monetary(data,'price',currency_code(data.get('currency')),0.001),'currency':currency_code(data.get('currency')),'description':clean(data.get('description'),4000)},peer=target['tenant_id']),extra
        if kind=='message':
            target=record(c,int(data.get('context_id',0)));require(visible(u,target),'Not found',404)
            require(target['tenant_id']!=u['tenant_id'] or target['peer_tenant'],'Select an external conversation',400)
            peer=target['tenant_id'] if target['tenant_id']!=u['tenant_id'] else target['peer_tenant']
            require(clean(data.get('description')),'Message required',400)
            return add(c,u,kind,{'context_id':target['id'],'title':json.loads(target['data']).get('title','Conversation'),'description':clean(data.get('description'),4000)},'sent',peer),extra
        if kind=='dispute':
            target=record(c,int(data.get('order_id',0)));require(target['kind']=='order' and u['tenant_id'] in (target['tenant_id'],target['peer_tenant']),'Order unavailable',404)
            v=sanitize(kind,data);v['order_id']=target['id'];v['currency']=json.loads(target['data'])['currency'];v['amount']=monetary(data,'amount',v['currency']);require(v['amount']<=json.loads(target['data'])['total'],'Amount exceeds order total',400)
            peer=target['peer_tenant'] if u['tenant_id']==target['tenant_id'] else target['tenant_id']
            return add(c,u,kind,v,peer=peer),extra
        if kind=='review':
            target=record(c,int(data.get('order_id',0)));require(target['kind']=='order' and target['tenant_id']==u['tenant_id'] and target['status']=='completed','A completed purchase is required',400)
            rating=number(data,'rating',1);require(rating<=5,'Rating must be 1–5',400)
            return add(c,u,kind,{'order_id':target['id'],'title':json.loads(target['data'])['title'],'rating':rating,'description':clean(data.get('description'),2000)},'submitted',target['peer_tenant']),extra
        raise Error(400,'Unsupported operation')
    match=re.fullmatch(r'/api/records/(\d+)',path)
    if match and method in {'PATCH','DELETE'}:
        r=record(c,int(match[1]));own=r['tenant_id']==u['tenant_id'];admin=u['role']=='super_admin'
        require(own or admin or r['peer_tenant']==u['tenant_id'],'Not found',404)
        if method=='DELETE':
            require((own or admin) and r['kind'] in {'product','rfq','job','address','campaign'},'Record cannot be deleted')
            c.execute('UPDATE records SET status=?,updated=? WHERE id=?',('archived',now(),r['id']));audit(c,u,'archive:'+r['kind'],r['id'])
        elif 'data' in d:
            require((own or admin) and r['kind'] in {'product','rfq','job','address','campaign'},'Record cannot be edited')
            require(isinstance(d['data'],dict),'Expected record fields object',400)
            require(not c.execute('SELECT 1 FROM alibaba_offers WHERE product_id=?',(r['id'],)).fetchone(),'Refresh imported products through Alibaba import',409)
            previous=json.loads(r['data']);incoming=dict(d['data']);incoming.setdefault('currency',previous.get('currency','USD'))
            require(incoming.get('currency')==previous.get('currency','USD'),'Cannot change a published record currency; create a new listing or request',409)
            data=sanitize(r['kind'],incoming)
            c.execute('UPDATE records SET data=?,status=?,updated=? WHERE id=?',(json.dumps(data),'pending' if r['kind']=='product' else r['status'],now(),r['id']));audit(c,u,'edit:'+r['kind'],r['id'])
        else:
            status=clean(d.get('status'));kind=r['kind'];old=r['status']
            if kind=='product':require(admin and status in {'published','rejected','archived'},'Moderator permission required')
            elif kind in {'verification','campaign','dispute'}:require(admin and status in {'approved','rejected','resolved','closed'},'Moderator permission required')
            elif kind=='order':
                transitions={'pending':{'accepted','cancelled'},'accepted':{'processing','cancelled'},'processing':{'shipped'},'shipped':{'completed'}}
                require(status in transitions.get(old,set()),'Invalid order transition',409)
                if not admin:
                    require((status in {'accepted','processing','shipped'} and r['peer_tenant']==u['tenant_id']) or (status in {'cancelled','completed'} and own),'Action belongs to the other party')
                if status=='cancelled':
                    od=json.loads(r['data'])
                    if od.get('stock_reserved'):
                        p=record(c,od['product_id']);pd=json.loads(p['data']);pd['stock']=float(pd['stock'])+od['quantity']
                        c.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(pd),p['id']))
                if status=='shipped':
                    od=json.loads(r['data']);od['tracking']=clean(d.get('tracking'));require(od['tracking'],'Tracking reference required',400)
                    c.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(od),r['id']))
            elif kind=='quote':
                require(r['peer_tenant']==u['tenant_id'] and old=='open' and status in {'accepted','rejected'},'Only the buyer may decide an open quote')
                if status=='accepted':
                    rfq=record(c,json.loads(r['data'])['rfq_id']);require(rfq['status']=='published','RFQ already awarded',409)
                    qd=json.loads(r['data']);add(c,u,'order',{'title':qd['title'],'quote_id':r['id'],'quantity':qd['quantity'],'unit_price':qd['price'],'total':total_price(qd['price'],qd['quantity'],qd['currency']),'currency':qd['currency'],'payment_status':'unpaid'},'accepted',r['tenant_id'])
                    c.execute('UPDATE records SET status=? WHERE id=?',('closed',rfq['id']))
            elif kind=='application':
                require(r['peer_tenant']==u['tenant_id'] and old=='open' and status in {'accepted','rejected'},'Only the job owner may decide an open application')
                if status=='accepted':
                    job=record(c,json.loads(r['data'])['job_id']);require(job['status']=='published','Job already awarded',409)
                    c.execute('UPDATE records SET status=?,peer_tenant=? WHERE id=?',('assigned',r['tenant_id'],job['id']))
            elif kind=='job':require(own and (old,status) in {('published','closed'),('assigned','in_progress'),('in_progress','completed')},'Invalid work order transition',409)
            elif kind in {'rfq','ticket'}:require((own or admin) and status=='closed','Cannot change status')
            else:raise Error(400,'Unsupported status change')
            c.execute('UPDATE records SET status=?,updated=? WHERE id=?',(status,now(),r['id']));audit(c,u,'status:'+kind+':'+status,r['id'])
        return output(c,record(c,r['id'])),extra
    if path=='/api/team':
        require(u['role'] in {'tenant_admin','super_admin'} or c.execute('SELECT COUNT(*) FROM users WHERE tenant_id=?',(u['tenant_id'],)).fetchone()[0]==1,'Tenant administrator required')
        if method=='GET':return {'items':[person(c,r[0]) for r in c.execute('SELECT id FROM users WHERE tenant_id=?',(u['tenant_id'],))]},extra
        require(method=='POST','Method not allowed',405)
        require(d.get('role') in {'buyer','supplier','provider','tenant_admin'},'Invalid role',400)
        email=clean(d.get('email')).lower();require(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email),'Valid email required',400)
        require(len(d.get('password',''))>=12 and clean(d.get('name')),'Name and a 12-character temporary password are required',400)
        require(not c.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone(),'Email already registered',409)
        uid=c.execute('INSERT INTO users(tenant_id,name,email,password,role,created) VALUES (?,?,?,?,?,?)',(u['tenant_id'],clean(d['name']),email,password_hash(d['password']),d['role'],now())).lastrowid
        # Founder becomes explicit tenant admin when the first colleague is added.
        if u['role']!='super_admin':c.execute('UPDATE users SET role=? WHERE id=?',('tenant_admin',u['id']))
        audit(c,u,'team:add',uid);return person(c,uid),extra
    if path.startswith('/api/admin'):
        require(u['role']=='super_admin','Super administrator required')
        if path=='/api/admin/alibaba' and method=='GET':
            return {'markup_percent':30,'imported_products':c.execute('SELECT COUNT(*) FROM alibaba_offers').fetchone()[0],'last_sync':c.execute('SELECT MAX(synced) FROM alibaba_offers').fetchone()[0],'live_api_connected':False},extra
        if path=='/api/admin/alibaba/import':
            require(method=='POST','Method not allowed',405)
            return alibaba_import.sync(c,u,d,__import__(__name__)),extra
        if path=='/api/admin/overview' and method=='GET':
            return {'users':c.execute('SELECT COUNT(*) FROM users').fetchone()[0],'tenants':c.execute('SELECT COUNT(*) FROM tenants').fetchone()[0],'orders':c.execute("SELECT COUNT(*) FROM records WHERE kind='order'").fetchone()[0],'pending':c.execute("SELECT COUNT(*) FROM records WHERE status='pending'").fetchone()[0]},extra
        if path=='/api/admin/users' and method=='GET':return {'items':[person(c,r[0]) for r in c.execute('SELECT id FROM users ORDER BY id DESC')]},extra
        if path=='/api/admin/tenants' and method=='GET':return {'items':[dict(r) for r in c.execute('SELECT * FROM tenants ORDER BY id DESC')]},extra
        if path=='/api/admin/audit' and method=='GET':return {'items':[dict(r) for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 500')]},extra
        if path=='/api/admin/settings' and method=='PATCH':
            for k,v in d.items():
                require(k in DEFAULTS,'Unknown setting',400)
                if k=='default_currency':require(v=='NGN','Marketplace default currency is NGN',400)
                if k=='currencies':require(v==DEFAULTS['currencies'],'Currency catalog is managed by the application',400)
                if k=='payments_enabled':require(v is False,'Live payment provider integration is not installed',409)
                require(type(v) is type(DEFAULTS[k]),'Invalid setting type: '+k,400)
                if k in {'commission_percent','seller_monthly_usd'}: require(0<=v<=10000,'Invalid price',400)
                c.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps(v),k))
            audit(c,u,'settings:update');return settings(c),extra
        m=re.fullmatch(r'/api/admin/(users|tenants)/(\d+)',path)
        if m and method=='PATCH':
            table=m[1];rid=int(m[2]);status=d.get('status');require(status in {'active','suspended'},'Invalid status',400)
            require(not (table=='users' and rid==u['id']) and not(table=='tenants' and rid==u['tenant_id']),'Cannot suspend your own account',400)
            if table=='users':require(c.execute('SELECT role FROM users WHERE id=?',(rid,)).fetchone()[0]!='super_admin','Manage super administrators with server CLI')
            c.execute('UPDATE '+table+' SET status=? WHERE id=?',(status,rid));audit(c,u,table+':'+status,rid)
            return {'ok':True},extra
    raise Error(404,'Endpoint not found')


def application(env,start_response):
    status=200;extra=[];ctype='application/json; charset=utf-8';c=None
    try:
        path=env.get('PATH_INFO','/');method=env['REQUEST_METHOD']
        if path.startswith('/api/'):
            require(method in {'GET','POST','PATCH','DELETE'},'Method not allowed',405)
            size=int(env.get('CONTENT_LENGTH') or 0);require(0<=size<=(3000000 if path=='/api/attachments' else 100000),'Request too large',413)
            try:d=json.loads(env['wsgi.input'].read(size)) if size else {}
            except (ValueError,UnicodeError):raise Error(400,'Invalid JSON')
            require(isinstance(d,dict),'Expected JSON object',400)
            if method=='POST' and path in {'/api/register','/api/login','/api/recover','/api/reset'}:
                with connect() as limiter:
                    client_ip=env.get('REMOTE_ADDR','unknown')
                    if client_ip in {'127.0.0.1','::1'} and env.get('HTTP_X_REAL_IP'):
                        import ipaddress
                        try:client_ip=str(ipaddress.ip_address(env['HTTP_X_REAL_IP']))
                        except ValueError:pass
                    limit(limiter,'auth:'+client_ip,40)
            c=connect();c.execute('BEGIN IMMEDIATE' if method!='GET' else 'BEGIN')
            try:
                result,extra=api(c,env,method,path,d,parse_qs(env.get('QUERY_STRING','')));c.commit()
            except Error:
                # Persist rate counters, never partially commit business mutations.
                c.rollback();raise
            body=json.dumps(result).encode()
        else:
            require(method in {'GET','HEAD'},'Method not allowed',405)
            file=(ROOT/'static'/path.lstrip('/')).resolve()
            if path in {'/terms','/privacy','/copyright'}:file=ROOT/'static'/'legal'/(path[1:]+'.html')
            elif path=='/' or not Path(path).suffix:file=ROOT/'static'/'index.html'
            require(file.is_relative_to((ROOT/'static').resolve()) and file.is_file(),'Not found',404)
            body=file.read_bytes();ctype=mimetypes.guess_type(file)[0] or 'application/octet-stream'
    except Error as e:
        status=e.status;body=json.dumps({'error':e.message}).encode()
    except (ValueError,TypeError,KeyError,OverflowError):
        status=400;body=b'{"error":"Invalid request fields"}'
    except Exception:
        import traceback;traceback.print_exc();status=500;body=b'{"error":"Internal server error"}'
    finally:
        if c:c.close()
    headers=[('Content-Type',ctype),('Content-Length',str(len(body))),('X-Content-Type-Options','nosniff'),('X-Frame-Options','DENY'),('Referrer-Policy','same-origin'),('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"),('Cache-Control','no-store' if env.get('PATH_INFO','').startswith('/api/') else 'no-cache')]+extra
    start_response(str(status)+' '+{200:'OK',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',405:'Method Not Allowed',409:'Conflict',413:'Payload Too Large',429:'Too Many Requests',500:'Internal Server Error'}.get(status,'Error'),headers)
    return [b'' if env.get('REQUEST_METHOD')=='HEAD' else body]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['init','serve','admin','reset-code']);parser.add_argument('--email');args=parser.parse_args();init_db()
    if args.command=='serve':make_server('127.0.0.1',int(os.environ.get('PORT', '8097')),application).serve_forever()
    elif args.command=='admin':
        import getpass
        email=args.email or input('Admin email: ');password=os.environ.get('ABH_ADMIN_PASSWORD') or getpass.getpass('Admin password (12+ characters): ')
        require(len(password)>=12,'Password must have at least 12 characters',400)
        with connect() as c:
            require(not c.execute('SELECT 1 FROM users WHERE email=?',(email.lower(),)).fetchone(),'Email already registered',409)
            tid=c.execute('INSERT INTO tenants(name,country,created) VALUES (?,?,?)',('Africa Bulk Hub Operations','Nigeria',now())).lastrowid
            c.execute('INSERT INTO users(tenant_id,name,email,password,role,created) VALUES (?,?,?,?,?,?)',(tid,'Super administrator',email.lower(),password_hash(password),'super_admin',now()))
        print('Super administrator created. No default password is stored.')
    elif args.command=='reset-code':
        with connect() as c:
            r=c.execute('SELECT id FROM users WHERE email=?',(clean(args.email).lower(),)).fetchone();require(r,'Account not found',404)
            token=secrets.token_urlsafe(32);c.execute('DELETE FROM resets WHERE user_id=?',(r[0],));c.execute('INSERT INTO resets VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),r[0],now()+1800))
            print('Single-use code, valid 30 minutes: '+token)

if __name__=='__main__':main()
