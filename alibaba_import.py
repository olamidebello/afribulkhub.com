"""Import authorized, normalized Alibaba offers. Does not scrape or place purchases."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json

SCHEMA = '''CREATE TABLE IF NOT EXISTS alibaba_offers(
 external_id TEXT PRIMARY KEY, product_id INTEGER NOT NULL UNIQUE REFERENCES records(id),
 supplier_price TEXT NOT NULL, currency TEXT NOT NULL, source_time INTEGER NOT NULL,
 synced INTEGER NOT NULL);
'''
MARKUP = Decimal('1.30')


def init(c):
    c.execute(SCHEMA)


def sale_price(value, minor_units):
    try:
        price = Decimal(str(value))
        if not price.is_finite() or not 0 < price < Decimal('1e10'):
            raise ValueError('Invalid supplier price')
        unit = Decimal(1).scaleb(-minor_units)
        if price != price.quantize(unit):
            raise ValueError('Supplier price exceeds currency precision')
        return (price * MARKUP).quantize(unit, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError('Invalid supplier price') from exc


def fresh(c, product_id, app):
    row = c.execute('SELECT source_time FROM alibaba_offers WHERE product_id=?', (product_id,)).fetchone()
    app.require(not row or row[0] >= app.now()-86400,
                'Supplier offer expired; refresh Alibaba pricing before ordering', 409)


def sync(c, u, payload, app):
    app.require(u['role'] == 'super_admin', 'Super administrator required')
    app.require(isinstance(payload, dict), 'Expected feed object', 400)
    source_time = payload.get('generated_at')
    app.require(type(source_time) is int and app.now()-86400 <= source_time <= app.now()+60,
                'Feed must have a generated_at Unix timestamp within the last 24 hours', 400)
    offers = payload.get('offers')
    app.require(isinstance(offers, list) and 0 < len(offers) <= 250, 'Expected 1–250 offers', 400)
    created = updated = 0
    seen = set()
    for offer in offers:
        app.require(isinstance(offer, dict), 'Expected offer object', 400)
        external = offer.get('external_id')
        app.require(isinstance(external, str) and 0 < len(external.strip()) <= 200,
                    'Stable external_id required for each offer/SKU', 400)
        app.require(external not in seen, 'Duplicate external_id in feed', 400)
        seen.add(external)
        code = app.currency_code(offer.get('currency'))
        app.require(bool(offer.get('currency')), 'Explicit supplier currency required', 400)
        try:
            price = sale_price(offer.get('supplier_price'), app.currency_info()[code]['minor_units'])
        except ValueError as exc:
            raise app.Error(400, str(exc)) from exc
        app.require('stock' in offer and 'moq' in offer, 'Stock and MOQ required', 400)
        data = app.sanitize('product', dict(offer, price=float(price), currency=code))
        app.require(float(data['stock']).is_integer() and float(data['moq']).is_integer(),
                    'Stock and MOQ must be whole numbers', 400)
        previous = c.execute('SELECT * FROM alibaba_offers WHERE external_id=?', (external,)).fetchone()
        if previous:
            app.require(source_time > previous['source_time'], 'Feed timestamp must advance for existing offers', 409)
            app.require(previous['currency'] == code, 'Cannot change imported offer currency', 409)
            # All local orders remain unfulfilled upstream: do not release their reservation
            # on refresh, including orders marked completed locally.
            reserved = 0
            for row in c.execute("SELECT data FROM records WHERE kind='order' AND status!='cancelled'"):
                order = json.loads(row[0])
                if order.get('product_id') == previous['product_id']:
                    reserved += order['quantity']
            data['stock'] = max(0, data['stock']-reserved)
            c.execute('UPDATE records SET data=?,updated=? WHERE id=?',
                      (json.dumps(data), app.now(), previous['product_id']))
            pid = previous['product_id']; updated += 1
        else:
            pid = app.add(c, u, 'product', data, 'pending')['id']; created += 1
        c.execute('INSERT INTO alibaba_offers VALUES (?,?,?,?,?,?) ON CONFLICT(external_id) '
                  'DO UPDATE SET supplier_price=excluded.supplier_price, source_time=excluded.source_time, synced=excluded.synced',
                  (external, pid, str(offer['supplier_price']), code, source_time, app.now()))
    app.audit(c, u, 'alibaba:sync')
    return {'created': created, 'updated': updated, 'markup_percent': 30,
            'message': 'New products await moderation. Supplier purchasing is not connected.'}
