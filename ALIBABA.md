# Alibaba offer imports — 30% markup

Selling price is the supplier's unit price multiplied by **1.30**, rounded half up
to the supplier currency's supported precision. USD 100.00 becomes USD 130.00.
This is a markup on product cost. Shipping, duties, taxes, payment fees and currency
conversion are not included. Import refreshes always calculate from supplier cost,
never from the previous selling price. Existing orders keep their agreed price.

## Current capabilities

Super administrators can use **Platform operations → Alibaba API & keys** to import
authorized normalized JSON. New listings publish automatically, as requested. Subsequent imports
update the same listing's price and available stock, preserving its existing status.
Archived or rejected listings are not automatically reactivated.
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


## Super-admin API and key management

The Alibaba API & keys screen lets active super administrators provision local
App Key/Secret and access/refresh-token settings, replace credentials, remove
saved credentials, record token expiry, select production/sandbox metadata, pause
all imports, pause scheduled imports only, and control automatic publication.
The 30% markup remains fixed. Empty secret inputs retain saved values.
The configuration validator checks presence, decryptability and known expiry
locally; it does not authenticate against Alibaba or refresh OAuth tokens.
Removing credentials disables imports locally; provider-side revocation must
be performed at Alibaba. This screen cannot issue Alibaba-approved keys.

Secrets are encrypted using Fernet in a dedicated integration table. Only
configured/not-configured indicators are returned to the browser; secret values
are absent from public settings, product records and audit events. Settings
updates use revision checks to prevent overwriting another administrator's edits.
All routes require super-admin authentication and the normal CSRF protection.

The encryption key is created on first credential save with mode 0600 at
`/var/lib/afribulkhub/api-credentials.key` by default. The application service user
must be able to read it. `ABH_CREDENTIAL_KEY_FILE` can override that path. Back up
this key privately and separately from database exports; losing it makes saved
credentials unreadable. Do not overwrite it on redeployment. The existing deploy
playbook preserves the data directory. A missing key causes credential updates to
fail instead of silently replacing the key. Credentials removed from the current
database may still exist encrypted in historical backups.


## Pull and install on the hosting server

Run as root on the server currently hosting afribulkhub.com. This installs the
Alibaba feature branch directly, so it does not depend on PR 1 being merged.

```bash
apt-get update
apt-get install -y git ansible
ansible-pull -U https://github.com/olamidebello/afribulkhub.com.git \
  -C alibaba-import-markup -i localhost, -c local \
  -d /opt/afribulkhub-alibaba-bootstrap deploy/pull-and-install.yml
```

Repeat the same command to update. The playbook pulls into a separate source
checkout, backs up the existing SQLite database, preserves accounts and the
credential encryption key, installs Python dependencies, initializes new tables,
selects an available backend port, restarts the service, checks Nginx/HTTPS and
verifies the feed timer and credential decryption. Source edits cause Git to stop
rather than being discarded. The Apps Store is not modified by this entrypoint.
Check normal Ansible output for any failing task; no server execution is implied
by committing this script.

After merging PR 1, change `-C alibaba-import-markup` to `-C main` and append
`-e hub_version=main` to install from main. The default domain, paths and admin
email can also be overridden with Ansible extra variables. Run the command only
on the intended hosting server; it does not change DNS.

After installation, sign in and open `https://afribulkhub.com/#alibaba`.
The API adapter and an approved product feed are still required to populate
real Alibaba listings; installing this playbook does not manufacture credentials
or supplier inventory.
