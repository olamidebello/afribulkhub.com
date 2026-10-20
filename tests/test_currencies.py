import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from test_app import MarketplaceTests as Fixture,Client
class CurrencyTests(unittest.TestCase):
    setUp=Fixture.setUp
    tearDown=Fixture.tearDown
    def product(self,code='NGN',price=100):
        status,p=self.seller.add('product',title='Currency test',description='Product',price=price,moq=1,stock=100,currency=code)
        self.assertEqual(status,200,p)
        self.assertEqual(self.admin.req('/api/records/'+str(p['id']),'PATCH',{'status':'published'})[0],200)
        return p
    def test_catalog_naira_and_afira_metadata(self):
        code,data=Client().req('/api/currencies');self.assertEqual(code,200);self.assertEqual(data['default'],'NGN')
        rows={r['code']:r for r in data['currencies']};self.assertEqual(len(rows),47)
        for code in ['NGN','ZAR','KES','GHS','XOF','XAF','ZWG','SLE','STN','MRU']:self.assertIn(code,rows)
        afr=rows['AFR'];self.assertEqual(afr['symbol'],'Ⱥ');self.assertEqual(afr['pronunciation'],'Ah-FEE-rah');self.assertEqual(afr['subdivision_ratio'],100);self.assertFalse(afr['iso_4217']);self.assertEqual(afr['examples'],['Ⱥ10','Ⱥ250','Ⱥ1,000'])
        self.assertNotIn('exchange_rate',afr)
    def test_default_and_user_preference_isolation(self):
        _,p=self.seller.add('product',title='Default',price=100,moq=1,stock=10);self.assertEqual(p['data']['currency'],'NGN')
        self.assertEqual(self.seller.req('/api/currency','PATCH',{'currency':'KES'},csrf=False)[0],403)
        self.assertEqual(self.seller.req('/api/currency','PATCH',{'currency':'KES'})[0],200)
        _,p=self.seller.add('product',title='Preference',price=100,moq=1,stock=10);self.assertEqual(p['data']['currency'],'KES')
        self.assertEqual(self.buyer.req('/api/currency')[1]['currency'],'NGN')
        self.assertEqual(self.seller.req('/api/currency','PATCH',{'currency':'NGN-FAKE'})[0],400)
        client=Client();_,s=client.req('/api/login','POST',{'email':'seller@test.com','password':'a-secure-password!'});self.assertEqual(s['user']['currency'],'KES')
    def test_order_and_mixed_cart_preserve_listing_currencies(self):
        ngn=self.product('NGN',500);kes=self.product('KES',100)
        for p in [ngn,kes]:self.assertEqual(self.buyer.req('/api/cart','POST',{'product_id':p['id'],'quantity':2})[0],200)
        status,result=self.buyer.req('/api/checkout','POST',{'delivery_address':'Lagos','currency':'AFR'})
        self.assertEqual(status,200);orders={r['data']['currency']:r['data'] for r in result['items']};self.assertEqual(orders['NGN']['total'],1000);self.assertEqual(orders['KES']['total'],200)
        self.assertEqual(self.seller.req('/api/records/'+str(ngn['id']),'PATCH',{'data':dict(ngn['data'],currency='USD')})[0],409)
    def test_afira_quote_order_and_dispute_snapshots(self):
        _,r=self.buyer.add('rfq',title='Request',description='Goods',quantity=10,budget=500,currency='NGN')
        status,q=self.seller.add('quote',rfq_id=r['id'],price=12.34,quantity=10,currency='AFR');self.assertEqual(status,200)
        self.assertEqual(self.buyer.req('/api/records/'+str(q['id']),'PATCH',{'status':'accepted'})[0],200)
        o=self.buyer.req('/api/records?kind=order&mine=1')[1]['items'][0];self.assertEqual(o['data']['currency'],'AFR');self.assertEqual(o['data']['total'],123.4)
        status,d=self.buyer.add('dispute',order_id=o['id'],title='Issue',description='Review',amount=10,currency='USD');self.assertEqual(status,200);self.assertEqual(d['data']['currency'],'AFR')
    def test_minor_units_and_total_rounding(self):
        self.assertEqual(self.seller.add('product',title='Invalid cents',price=1.005,currency='AFR',moq=1,stock=5)[0],400)
        self.assertEqual(self.seller.add('product',title='Invalid fraction',price=.5,currency='XAF',moq=1,stock=5)[0],400)
        p=self.product('TND',.001);status,o=self.buyer.add('order',product_id=p['id'],quantity=3,currency='NGN');self.assertEqual(status,200);self.assertEqual(o['data']['total'],.003);self.assertEqual(o['data']['currency'],'TND')
    def test_legacy_usd_migration_is_idempotent(self):
        p=self.product('USD',12.5)
        with app.connect() as c:
            legacy=dict(p['data']);legacy.pop('currency');c.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(legacy),p['id']))
            c.execute("DELETE FROM schema_migrations WHERE name='currencies-v1'");c.execute('UPDATE settings SET value=? WHERE key=?',('["USD"]','currencies'))
        app.init_db();app.init_db()
        p=self.seller.req('/api/records/'+str(p['id']))[1];self.assertEqual(p['data']['currency'],'USD');self.assertEqual(p['data']['price'],12.5)
        status,o=self.buyer.add('order',product_id=p['id'],quantity=2);self.assertEqual(status,200);self.assertEqual(o['data']['currency'],'USD');self.assertEqual(o['data']['total'],25)
        self.assertEqual(self.buyer.req('/api/settings')[1]['default_currency'],'NGN')
del Fixture
if __name__=='__main__':unittest.main()
