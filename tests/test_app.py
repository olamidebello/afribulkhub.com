import io
import json
import os
import tempfile
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app

class Client:
    counter=0
    def __init__(self):
        Client.counter+=1;self.ip='127.0.0.'+str(Client.counter);self.cookie='';self.csrf=''
    def req(self,path,method='GET',data=None,csrf=True):
        from urllib.parse import urlsplit
        p=urlsplit(path);body=json.dumps(data or {}).encode();status=[];headers=[]
        env={'REQUEST_METHOD':method,'PATH_INFO':p.path,'QUERY_STRING':p.query,'CONTENT_LENGTH':str(len(body)),'wsgi.input':io.BytesIO(body),'HTTP_HOST':'localhost','HTTP_COOKIE':self.cookie,'REMOTE_ADDR':self.ip}
        if csrf:env['HTTP_X_CSRF_TOKEN']=self.csrf
        def start(s,h):status.append(int(s.split()[0]));headers.extend(h)
        raw=b''.join(app.application(env,start))
        for k,v in headers:
            if k=='Set-Cookie':self.cookie=v.split(';')[0]
        val=json.loads(raw) if any(k=='Content-Type' and 'json' in v for k,v in headers) else raw
        if isinstance(val,dict) and 'csrf' in val:self.csrf=val['csrf'] or ''
        return status[0],val
    def register(self,email,role='buyer'):
        return self.req('/api/register','POST',{'email':email,'password':'a-secure-password!','name':email.split('@')[0],'company':email,'country':'Nigeria','role':role})
    def add(self,kind,**data):return self.req('/api/records','POST',{'kind':kind,'data':data})

class MarketplaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();app.DB=os.path.join(self.temp.name,'test.db');app.init_db()
        self.buyer=Client();self.seller=Client();self.outsider=Client();self.admin=Client()
        for c,email,role in [(self.buyer,'buyer@test.com','buyer'),(self.seller,'seller@test.com','supplier'),(self.outsider,'other@test.com','buyer'),(self.admin,'admin@test.com','buyer')]:self.assertEqual(c.register(email,role)[0],200)
        with app.connect() as db:db.execute("UPDATE users SET role='super_admin' WHERE email='admin@test.com'")
    def tearDown(self):self.temp.cleanup()
    def product(self,stock=100):
        status,p=self.seller.add('product',title='Solar kit',description='Real product',category='Energy',price=12.5,moq=5,stock=stock,country='Nigeria',unit='set')
        self.assertEqual(status,200);self.assertEqual(p['status'],'pending')
        self.assertEqual(self.admin.req('/api/records/'+str(p['id']),'PATCH',{'status':'published'})[0],200)
        return p
    def order(self):
        p=self.product();status,o=self.buyer.add('order',product_id=p['id'],quantity=10,total=.01,delivery_address='Lagos')
        self.assertEqual(status,200);self.assertEqual(o['data']['total'],125)
        return p,o
    def test_identity_csrf_and_role_escalation(self):
        self.assertEqual(Client().register('hack@test.com','super_admin')[0],400)
        self.assertEqual(self.buyer.add('product',title='bad')[0],403)
        self.assertEqual(self.buyer.req('/api/profile','PATCH',{'name':'New'},csrf=False)[0],403)
        self.assertEqual(self.buyer.req('/api/admin/users')[0],403)
        self.assertEqual(self.buyer.req('/api/profile','PATCH',{'name':'Good','role':'super_admin'})[0],200)
        self.assertEqual(self.buyer.req('/api/admin/users')[0],403)
    def test_moderation_and_public_visibility(self):
        _,p=self.seller.add('product',title='Pending',price=2,moq=1,stock=5)
        self.assertEqual(Client().req('/api/records/'+str(p['id']))[0],404)
        self.assertEqual(self.buyer.req('/api/records/'+str(p['id']),'PATCH',{'status':'published'})[0],404)
        self.admin.req('/api/records/'+str(p['id']),'PATCH',{'status':'published'})
        self.assertEqual(len(Client().req('/api/records?kind=product')[1]['items']),1)
    def test_order_price_inventory_and_transitions(self):
        p,o=self.order();url='/api/records/'+str(o['id'])
        self.assertEqual(self.seller.req('/api/records/'+str(p['id']))[1]['data']['stock'],90)
        self.assertEqual(self.buyer.req(url,'PATCH',{'status':'accepted'})[0],403)
        self.assertEqual(self.seller.req(url,'PATCH',{'status':'shipped'})[0],409)
        for status in ['accepted','processing']:
            self.assertEqual(self.seller.req(url,'PATCH',{'status':status})[0],200)
        self.assertEqual(self.seller.req(url,'PATCH',{'status':'shipped'})[0],400)
        self.assertEqual(self.seller.req(url,'PATCH',{'status':'shipped','tracking':'DHL 123'})[0],200)
        self.assertEqual(self.buyer.req(url,'PATCH',{'status':'completed'})[0],200)
        self.assertEqual(self.buyer.add('review',order_id=o['id'],rating=5,description='Good')[0],200)
    def test_cross_tenant_private_records(self):
        _,o=self.order();url='/api/records/'+str(o['id'])
        self.assertEqual(self.outsider.req(url)[0],404)
        self.assertEqual(self.outsider.req(url,'PATCH',{'status':'cancelled'})[0],404)
        self.assertEqual(self.outsider.req('/api/records?kind=order&mine=1')[1]['items'],[])
        self.assertEqual(self.seller.req(url)[0],200)
        self.assertEqual(self.admin.req(url)[0],200)
    def test_stock_validation_and_cancellation(self):
        p,o=self.order()
        self.assertEqual(self.buyer.add('order',product_id=p['id'],quantity=1000)[0],400)
        self.assertEqual(self.buyer.add('order',product_id=p['id'],quantity=5.5)[0],400)
        url='/api/records/'+str(o['id'])
        self.assertEqual(self.buyer.req(url,'PATCH',{'status':'cancelled'})[0],200)
        self.assertEqual(self.buyer.req(url,'PATCH',{'status':'cancelled'})[0],409)
        self.assertEqual(self.seller.req('/api/records/'+str(p['id']))[1]['data']['stock'],100)
    def test_quote_to_order_once(self):
        _,r=self.buyer.add('rfq',title='Need solar',description='100 kits',quantity=100,budget=2000)
        _,q=self.seller.add('quote',rfq_id=r['id'],price=10,quantity=100,description='Delivery in 7 days')
        self.assertEqual(self.outsider.req('/api/records/'+str(q['id']))[0],404)
        self.assertEqual(self.buyer.req('/api/records/'+str(q['id']),'PATCH',{'status':'accepted'})[0],200)
        self.assertEqual(self.buyer.req('/api/records/'+str(q['id']),'PATCH',{'status':'accepted'})[0],403)
        orders=self.buyer.req('/api/records?kind=order&mine=1')[1]['items'];self.assertEqual(len(orders),1);self.assertEqual(orders[0]['data']['total'],1000)
    def test_service_work_assignment(self):
        _,j=self.buyer.add('job',title='Install solar',location='Abuja',description='Installation',budget=100)
        _,a=self.seller.add('application',job_id=j['id'],price=90,description='Qualified installer')
        self.assertEqual(self.buyer.req('/api/records/'+str(a['id']),'PATCH',{'status':'accepted'})[0],200)
        for status in ['in_progress','completed']:
            self.assertEqual(self.buyer.req('/api/records/'+str(j['id']),'PATCH',{'status':status})[0],200)
        self.assertEqual(self.seller.req('/api/records/'+str(j['id']))[0],200)
    def test_messages_disputes_and_support_privacy(self):
        p,o=self.order();_,msg=self.buyer.add('message',context_id=o['id'],description='When will this ship?')
        self.assertEqual(self.seller.req('/api/records/'+str(msg['id']))[0],200)
        self.assertEqual(self.outsider.req('/api/records/'+str(msg['id']))[0],404)
        self.assertEqual(self.seller.add('message',context_id=msg['id'],description='Tomorrow')[0],200)
        self.assertEqual(self.buyer.add('dispute',order_id=o['id'],title='Problem',description='Damaged',amount=1000)[0],400)
        _,d=self.buyer.add('dispute',order_id=o['id'],title='Problem',description='Damaged',amount=10)
        self.assertEqual(self.seller.req('/api/records/'+str(d['id']))[0],200)
        _,ticket=self.buyer.add('ticket',title='Help',description='Private support request')
        self.assertEqual(self.outsider.req('/api/records/'+str(ticket['id']))[0],404)
    def test_team_invites_and_tenant_access(self):
        _,o=self.order()
        self.assertEqual(self.buyer.req('/api/team','POST',{'name':'Colleague','email':'team@test.com','password':'good-long-password','role':'super_admin'})[0],400)
        self.assertEqual(self.buyer.req('/api/team','POST',{'name':'Colleague','email':'team@test.com','password':'good-long-password','role':'buyer'})[0],200)
        team=Client();self.assertEqual(team.req('/api/login','POST',{'email':'team@test.com','password':'good-long-password'})[0],200)
        self.assertEqual(team.req('/api/records/'+str(o['id']))[0],200)
        self.assertEqual(team.req('/api/team','POST',{'name':'Bad','email':'bad@test.com','password':'good-long-password','role':'supplier'})[0],403)
    def test_suspension_revokes_session(self):
        uid=self.buyer.req('/api/session')[1]['user']['id']
        self.assertEqual(self.admin.req('/api/admin/users/'+str(uid),'PATCH',{'status':'suspended'})[0],200)
        self.assertEqual(self.buyer.req('/api/session')[1]['user'],None)
        self.assertEqual(self.buyer.add('rfq',title='Blocked')[0],401)
    def test_settings_cannot_fake_live_payments(self):
        self.assertEqual(self.admin.req('/api/admin/settings','PATCH',{'payments_enabled':True})[0],409)
        self.assertEqual(self.buyer.req('/api/admin/settings','PATCH',{'commission_percent':3})[0],403)
        self.assertEqual(self.admin.req('/api/admin/settings','PATCH',{'commission_percent':3})[0],200)
    def test_static_and_bad_requests(self):
        self.assertEqual(Client().req('/')[0],200)
        self.assertEqual(Client().req('/../app.py')[0],404)
        self.assertEqual(self.buyer.req('/api/records','POST',[])[0],400)
        self.assertEqual(self.buyer.req('/api/records/garbage')[0],400)
    def test_password_change_invalidates_sessions(self):
        self.assertEqual(self.buyer.req('/api/password','POST',{'current':'wrong','password':'new-long-password'})[0],400)
        self.assertEqual(self.buyer.req('/api/password','POST',{'current':'a-secure-password!','password':'new-long-password'})[0],200)
        self.assertIsNone(self.buyer.req('/api/session')[1]['user'])
        self.assertEqual(self.buyer.req('/api/login','POST',{'email':'buyer@test.com','password':'a-secure-password!'})[0],401)
        self.assertEqual(self.buyer.req('/api/login','POST',{'email':'buyer@test.com','password':'new-long-password'})[0],200)
    def test_cart_reprices_and_checkout_is_atomic(self):
        p=self.product(stock=20)
        self.assertEqual(self.buyer.req('/api/cart','POST',{'product_id':p['id'],'quantity':5})[0],200)
        self.assertEqual(len(self.buyer.req('/api/cart')[1]['items']),1)
        self.assertEqual(self.outsider.req('/api/cart')[1]['items'],[])
        code,result=self.buyer.req('/api/checkout','POST',{'delivery_address':'Lagos','total':0})
        self.assertEqual(code,200);self.assertEqual(result['items'][0]['data']['total'],62.5)
        self.assertEqual(self.buyer.req('/api/cart')[1]['items'],[])
        self.assertEqual(self.buyer.req('/api/checkout','POST',{'delivery_address':'Lagos'})[0],400)
        self.assertEqual(self.buyer.req('/api/cart','POST',{'product_id':p['id'],'quantity':15})[0],200)
        self.outsider.add('order',product_id=p['id'],quantity=10)
        self.assertEqual(self.buyer.req('/api/checkout','POST',{'delivery_address':'Lagos'})[0],409)
        self.assertEqual(self.seller.req('/api/records/'+str(p['id']))[1]['data']['stock'],5)
    def test_attachment_access_type_and_storefront(self):
        import base64
        p,o=self.order()
        content=base64.b64encode(b'%PDF-1.4 test evidence').decode()
        code,a=self.buyer.req('/api/attachments','POST',{'record_id':o['id'],'filename':'evidence.pdf','content':content})
        self.assertEqual(code,200)
        self.assertEqual(self.seller.req('/api/attachments/'+str(a['id']))[0],200)
        self.assertEqual(self.outsider.req('/api/attachments/'+str(a['id']))[0],404)
        self.assertEqual(Client().req('/api/attachments/'+str(a['id']))[0],401)
        self.assertEqual(self.outsider.req('/api/attachments','POST',{'record_id':p['id'],'filename':'bad.pdf','content':content})[0],403)
        self.assertEqual(self.buyer.req('/api/attachments','POST',{'record_id':o['id'],'filename':'bad.html','content':base64.b64encode(b'<script>alert(1)</script>').decode()})[0],400)
        store=Client().req('/api/stores/'+str(p['tenant_id']))
        self.assertEqual(store[0],200);self.assertEqual(len(store[1]['products']),1)
        self.assertNotIn('email',store[1]['store'])
    def test_rate_limit_persists_on_failed_login(self):
        bad=Client()
        for i in range(40):self.assertEqual(bad.req('/api/login','POST',{'email':'no@test.com','password':'bad'})[0],401)
        self.assertEqual(bad.req('/api/login','POST',{'email':'no@test.com','password':'bad'})[0],429)

if __name__=='__main__':unittest.main()
