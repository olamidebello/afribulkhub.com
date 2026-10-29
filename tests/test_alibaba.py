import json
from decimal import Decimal
import unittest
import test_app
from test_app import Client
from alibaba_import import sale_price
import app


class AlibabaTests(unittest.TestCase):
    setUp = test_app.MarketplaceTests.setUp
    tearDown = test_app.MarketplaceTests.tearDown
    def feed(self, **changes):
        offer = dict(external_id='supplier-1/sku-1', title='Wholesale solar kit',
                     supplier_price='100.00', currency='USD', moq=1, stock=100)
        offer.update(changes)
        return dict(generated_at=app.now()-10, offers=[offer])

    def test_pricing_precision(self):
        self.assertEqual(sale_price('100.00', 2), Decimal('130.00'))
        self.assertEqual(sale_price('0.05', 2), Decimal('0.07'))
        self.assertEqual(sale_price('105', 0), Decimal('137'))
        for value in ['NaN', 'Infinity', '-1', '0', '1.001']:
            with self.assertRaises(ValueError): sale_price(value, 2)

    def test_import_permissions_and_private_cost(self):
        endpoint = '/api/admin/alibaba/import'
        self.assertEqual(self.buyer.req(endpoint,'POST',self.feed())[0],403)
        self.assertEqual(self.admin.req(endpoint,'POST',self.feed(),csrf=False)[0],403)
        status, result = self.admin.req(endpoint,'POST',self.feed())
        self.assertEqual(status,200); self.assertEqual(result['created'],1)
        rows=self.admin.req('/api/records?kind=product')[1]['items']
        self.assertEqual(rows[0]['data']['price'],130)
        self.assertEqual(rows[0]['status'],'published')
        self.assertNotIn('supplier_price',json.dumps(rows))
        public = Client().req('/api/records?kind=product')[1]['items']
        self.assertEqual(len(public),1)
        self.assertEqual(public[0]['data']['price'],130)
        self.assertNotIn('supplier_price',json.dumps(public))
        self.assertEqual(self.admin.req('/api/records/'+str(rows[0]['id']),'PATCH',{'data':rows[0]['data']})[0],409)

    def test_sync_preserves_orders_and_does_not_compound(self):
        url='/api/admin/alibaba/import';self.admin.req(url,'POST',self.feed())
        product=self.admin.req('/api/records?kind=product')[1]['items'][0];pid=product['id']
        self.admin.req('/api/records/'+str(pid),'PATCH',{'status':'published'})
        status,order=self.buyer.add('order',product_id=pid,quantity=10)
        self.assertEqual(status,200);self.assertEqual(order['data']['total'],1300)
        feed=self.feed();feed['generated_at']+=1
        self.assertEqual(self.admin.req(url,'POST',feed)[0],200)
        refreshed=self.admin.req('/api/records/'+str(pid))[1]
        self.assertEqual(refreshed['data']['price'],130)
        self.assertEqual(refreshed['data']['stock'],90)
        self.assertEqual(refreshed['status'],'published')
        self.assertEqual(self.admin.req(url,'POST',feed)[0],409)
        feed['generated_at']+=1;feed['offers'][0]['supplier_price']='120.00'
        self.assertEqual(self.admin.req(url,'POST',feed)[0],200)
        self.assertEqual(self.admin.req('/api/records/'+str(order['id']))[1]['data']['total'],1300)
        self.assertEqual(self.admin.req('/api/records/'+str(pid))[1]['data']['price'],156)

    def test_atomic_feed_validation_and_expiry(self):
        feed=self.feed();feed['offers'].append(dict(feed['offers'][0],external_id='bad',supplier_price='NaN'))
        self.assertEqual(self.admin.req('/api/admin/alibaba/import','POST',feed)[0],400)
        self.assertEqual(self.admin.req('/api/admin/alibaba')[1]['imported_products'],0)
        self.admin.req('/api/admin/alibaba/import','POST',self.feed())
        pid=self.admin.req('/api/records?kind=product')[1]['items'][0]['id']
        self.admin.req('/api/records/'+str(pid),'PATCH',{'status':'published'})
        self.buyer.req('/api/cart','POST',{'product_id':pid,'quantity':1})
        with app.connect() as c:c.execute('UPDATE alibaba_offers SET source_time=?',(app.now()-86401,))
        self.assertEqual(self.buyer.add('order',product_id=pid,quantity=1)[0],409)
        self.assertEqual(self.buyer.req('/api/checkout','POST',{'delivery_address':'Lagos'})[0],409)
