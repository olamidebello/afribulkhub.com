# Africa Bulk Hub

Original wholesale sourcing and service-work marketplace for **afribulkhub.com**, deployable alongside Olamidepanel on Debian 12. This first implementation combines Alibaba-style sourcing with Field Nation-inspired service work; it is not a copy, affiliated product, or feature-complete equivalent of either platform.

## Implemented and connected

- Responsive public homepage, category browsing, product search, product detail/specification pages, supplier storefronts, saved products, a persistent cart and atomic multi-supplier order creation, and original Africa-centered visual branding. Example listings on an empty homepage are labeled illustrations and cannot be ordered.
- Buyer, supplier, provider, tenant administrator, and super administrator accounts. Organization-scoped records, explicit counterparty sharing, persistent sessions, CSRF checks, scrypt password hashing, login throttling, suspension, profile and password changes. Founding accounts can add colleagues; after the first addition the founder becomes tenant administrator.
- Supplier product creation, editing, archival, MOQ/stock validation and super-admin publication moderation. Public RFQs; supplier quotations; buyer acceptance creates an order exactly once and closes the RFQ.
- Product orders use server-side prices, reserve inventory atomically, and enforce counterparty-specific transitions: pending → accepted → processing → shipped → completed. Pending/accepted buyer cancellations restore stock. Suppliers provide a carrier/tracking reference. Quote orders record negotiated quantity and prices without reserving catalog stock.
- Service job posting, provider applications, buyer award, assignment, work-in-progress and completion. The job owner controls completion in this version.
- Counterparty messages linked to records, support tickets, delivery addresses, business verification submissions, campaign approval requests, disputes with requested amounts, and completed-order reviews. PDF, PNG and JPEG specification/evidence attachments are limited to 2 MiB each and ten files per record. Private-record downloads enforce the same counterparty/tenant scope. Public-listing files are available to signed-in users. File signatures are checked; malware scanning is not installed.
- Super-admin overview, users/organization suspension, product moderation, RFQ/order/dispute/verification/campaign/support operations, editable platform/pricing settings, audit history and CSV exports.
- Ansible deployment: separate unprivileged service, production Gunicorn runtime, root-owned application, private SQLite data, pre-update backup, dedicated Nginx host, Let's Encrypt and public HTTPS health verification. Does not replace other domain vhosts.

## Explicit implementation boundaries

This is a tested core marketplace, **not the entire requested enterprise inventory**. No live payments, escrow, refunds, payouts, wallets, financing, subscriptions, tax calculation or buyer-protection guarantee. Commission and membership values are stored configuration, not billing. Dispute approval does not move money. The API refuses enabling live payments.

Not yet implemented: visual search and full media galleries; tiered prices and structured variants; shipping rate APIs and live carrier tracking; external KYC; translated messaging and localization; SMS/email/push delivery and email verification; self-service email reset; custom supplier storefront layout editor; ad delivery and attribution; coupons; bulk catalog import; customer CRM; live analytics; granular custom permissions and staff revocation GUI; mobile binaries and app-store distribution; durable job queues, external search index, accounting ledger, automated DNS, and panel inventory registration. These require further implementation, provider contracts/credentials, and operational testing. No placeholder button claims these services ran.

Private tenant records are visible to all members of that tenant; granular departmental scopes are not implemented. RFQs/jobs/products are intentionally public only when published. Platform super admins can access all records and their actions are audited. SQLite WAL with serialized writes fits a small single-server deployment; do not claim enterprise scale or multi-node readiness.

## Local verification

Python 3.11+ and Node 18+ (syntax checking only). No Python packages are needed for local tests:

```sh
python -m unittest discover -s tests -v
node --check static/app.js
python app.py init
ABH_SECURE_COOKIE=0 python app.py serve
```

Open `http://127.0.0.1:8097`. Disable secure cookies only on local loopback development. No demo users/passwords are created. The built-in server is for local development only.

Create an administrator in a separate terminal, using the same database environment:

```sh
python app.py admin --email you@example.com
```

The CLI prompts privately for a password of at least 12 characters. User accounts register through the website. Supplier products require super-admin publication.

## Deploy on the Olamidepanel server

The deployment runs **on the existing server**; it does not require or modify Olamidepanel internals. First point the Namecheap A record for `@` in `afribulkhub.com` to the hosting server (`181.214.149.146` if still current). Remove conflicting A/AAAA records. DNS provisioning is not included. No DNS credentials have been requested or stored.

On the Debian server:

```sh
sudo apt-get update
sudo apt-get install -y git ansible
sudo git clone https://github.com/olamidebello/afribulkhub.com.git /opt/afribulkhub-source
cd /opt/afribulkhub-source
sudo ansible-playbook -i localhost, -c local deploy/deploy.yml -e hub_email=YOUR_REAL_EMAIL
```

The playbook uses loopback port **8097**. Check this port is free before the first deployment; select another with `-e hub_port=PORT` if required. Subsequent deployments refuse an existing dedicated vhost whose port differs. It requires DNS pointing to the server and public ports 80/443 for certificate issuance. `www` is not provisioned; add it intentionally with matching DNS/certificate/vhost configuration if required. Existing dedicated vhosts are retained to preserve Certbot edits. On first install, inspect for duplicate `server_name afribulkhub.com` declarations in other Nginx vhosts before deploying.

Then create the super administrator:

```sh
sudo -u afribulkhub env ABH_DATABASE=/var/lib/afribulkhub/hub.db /opt/afribulkhub/venv/bin/python /opt/afribulkhub/app.py admin --email YOUR_REAL_EMAIL
```

Sign in at `https://afribulkhub.com` and open **Dashboard → Platform operations**. There is no default admin password. The Ansible installation never sends a password through command arguments.

### Olamidepanel GUI inventory

Register `afribulkhub.com` under the correct hosting account using the existing Olamidepanel Hosting Domains GUI. The app deployment does not know the panel owner/account ID and deliberately does not edit its MySQL database or overwrite its inventory. Service metadata is written to `/var/lib/afribulkhub/hosting-status.json` after successful deployment. Add a panel integration only after checking the installed panel's supported inventory API/schema.

### Update and inspect

```sh
cd /opt/afribulkhub-source
sudo git pull --ff-only
sudo ansible-playbook -i localhost, -c local deploy/deploy.yml -e hub_email=YOUR_REAL_EMAIL
sudo systemctl status afribulkhub --no-pager
curl --fail https://afribulkhub.com/api/health
sudo journalctl -u afribulkhub -n 80 --no-pager
```

The playbook creates a consistent `predeploy-*.db` snapshot before each update. It does not force-reset local modifications. Preserve app and data together when rolling back. First stop the service; back up the current database; restore a reviewed app revision and matching snapshot; restart and verify. Do not overwrite a running database. Backups include private information.

### Recovery and backups

After independently verifying the account owner, an operator can issue a 30-minute single-use code:

```sh
sudo -u afribulkhub env ABH_DATABASE=/var/lib/afribulkhub/hub.db /opt/afribulkhub/venv/bin/python /opt/afribulkhub/app.py reset-code --email USER_EMAIL
```

Deliver it securely to that user. Website **Sign in → Forgot password → I have a recovery code** accepts it. Codes are stored as hashes; a reset invalidates every existing session. No email delivery is claimed.

Run `deploy/backup.py` as the service user with access to the data directory for an integrity-checked SQLite backup, then replicate it to encrypted off-server storage. Attachments are inside the SQLite backup. No automatic retention or restoration has been configured.

## Launch gates and validation

Automated WSGI integration tests cover tenant isolation, public/private visibility, permissions, stock and price integrity, order transitions, quote conversion, work assignment, messages/disputes, team membership, suspension, CSRF, password changes and login throttling. JavaScript syntax is checked. Live Debian/Nginx/Certbot execution, browser layout verification, capacity tests and provider integration tests have not been performed in the authoring environment.

Complete operator contact/identity, jurisdiction, privacy retention and legal review of the draft Terms/Privacy pages before commercial launch. Set the support contact in super-admin settings. Configure backups and monitoring, run an independent security review, and complete real provider integrations before accepting money or advertising purchase protection.

© 2026 Africa Bulk Hub. All rights reserved.
