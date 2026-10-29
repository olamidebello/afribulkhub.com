# Alibaba offer imports — 30% markup

Selling price is the supplier's unit price multiplied by **1.30**, rounded half up
to the supplier currency's supported precision. USD 100.00 becomes USD 130.00.
This is a markup on product cost. Shipping, duties, taxes, payment fees and currency
conversion are not included. Import refreshes always calculate from supplier cost,
never from the previous selling price. Existing orders keep their agreed price.

## Current capabilities

Super administrators can use **Platform operations → Alibaba imports** to import
authorized normalized JSON. New listings enter moderation. Subsequent imports
update the same listing's price and available stock, preserving moderation status.
Supplier costs and offer identifiers are stored in a private table, outside the
public product data. Stable identifiers must distinguish supplier, product, SKU
and any fixed quantity tier. Do not import a negotiable price range as a fixed offer.

The deployment playbook installs a timer that checks a local feed every 15 minutes.
It skips when the file does not exist. An unchanged feed is skipped without changing
stock. New feeds must have advancing source timestamps within 24 hours. Direct orders
and cart checkout reject imported offers older than 24 hours. Local noncancelled
orders are subtracted from refreshed source stock because upstream fulfillment
is not connected. Omitted offers are not removed: partial batches are supported.

## Remaining live API setup

**This is an import pipeline, not a connected Alibaba API client.** No scraping,
automatic supplier search, upstream order placement, payment, or tracking sync is
implemented. Alibaba application approval, App Key/Secret, required sourcing API
permissions and applicable supplier authorization are still needed. The approved
API contracts determine the adapter; do not assume Alibaba Cloud or AliExpress
credentials or endpoints are interchangeable with Alibaba.com.

After access is approved, a server-side adapter must fetch the permitted offers,
normalize them to this contract and atomically replace the feed file. Keep secrets
in private server configuration, never in GitHub or product records. Only generate
a new timestamp after a successful complete fetch for that batch; do not refresh
timestamps on cached data. Publish stock as the source's actual unreserved inventory.
Until fulfillment integration exists, local orders remain unpaid marketplace records.

Official onboarding: https://openapi.alibaba.com/doc/doc.htm

## Feed contract

`generated_at` is the source fetch time in Unix seconds; replace the placeholder
below with the real fetch time. The example is illustrative, not a real supplier offer.

```json
{
  "generated_at": 0,
  "offers": [{
    "external_id": "supplier-id/product-id/sku-id/fixed-tier-id",
    "title": "Authorized supplier product",
    "description": "Supplier-approved product description",
    "supplier_price": "100.00",
    "currency": "USD",
    "moq": 10,
    "stock": 100,
    "unit": "piece",
    "country": "China",
    "category": "Wholesale"
  }]
}
```

Maximum 250 offers / 100000 bytes per batch. No implicit currency conversion.
Import through `POST /api/admin/alibaba/import` with the normal administrator
session and CSRF token, or configure the adapter to write
`/var/lib/afribulkhub/alibaba-offers.json` (readable by `afribulkhub`, mode 0600).
For timer imports, new listings belong to the configured administrator's organization.
Use a consistent administrator organization for manual imports of new offers.

Manual server run:

```bash
sudo -u afribulkhub env ABH_DATABASE=/var/lib/afribulkhub/hub.db \
  /opt/afribulkhub/venv/bin/python /opt/afribulkhub/sync_alibaba.py \
  --feed /var/lib/afribulkhub/alibaba-offers.json --email dobcalldemo@gmail.com
```

The timer can be inspected with `systemctl status afribulkhub-alibaba.timer` and
`journalctl -u afribulkhub-alibaba.service`. Existing pull-and-deploy instructions
apply after these changes are merged; source preparation does not deploy the server.
