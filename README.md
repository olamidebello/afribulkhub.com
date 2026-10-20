# Africa Bulk Hub

Original wholesale sourcing and service-work marketplace for **afribulkhub.com**, deployable alongside Olamidepanel on Debian 12. This first implementation combines Alibaba-style sourcing with Field Nation-inspired service work; it is not a copy, affiliated product, or feature-complete equivalent of either platform.

## Implemented and connected

- Responsive public homepage, category browsing, product search, product detail/specification pages, supplier storefronts, saved products, a persistent cart and atomic multi-supplier order creation, and the generated green-and-gold Africa Bulk Hub logo, app icon, banner and shared artwork. Example listings on an empty homepage are labeled illustrations and cannot be ordered.
- Buyer, supplier, provider, tenant administrator, and super administrator accounts. Organization-scoped records, explicit counterparty sharing, persistent sessions, CSRF checks, scrypt password hashing, login throttling, suspension, profile and password changes. Founding accounts can add colleagues; after the first addition the founder becomes tenant administrator.
- Supplier product creation, editing, archival, MOQ/stock validation and super-admin publication moderation. Public RFQs; supplier quotations; buyer acceptance creates an order exactly once and closes the RFQ.
- Product orders use server-side prices, reserve inventory atomically, and enforce counterparty-specific transitions: pending → accepted → processing → shipped → completed. Pending/accepted buyer cancellations restore stock. Suppliers provide a carrier/tracking reference. Quote orders record negotiated quantity and prices without reserving catalog stock.
- Service job posting, provider applications, buyer award, assignment, work-in-progress and completion. The job owner controls completion in this version.
- Counterparty messages linked to records, support tickets, delivery addresses, business verification submissions, campaign approval requests, disputes with requested amounts, and completed-order reviews. PDF, PNG and JPEG specification/evidence attachments are limited to 2 MiB each and ten files per record. Private-record downloads enforce the same counterparty/tenant scope. Public-listing files are available to signed-in users. File signatures are checked; malware scanning is not installed.
- Super-admin overview, users/organization suspension, product moderation, RFQ/order/dispute/verification/campaign/support operations, editable platform/pricing settings, audit history and CSV exports.
- Ansible deployment: separate unprivileged service, production Gunicorn runtime, root-owned application, private SQLite data, pre-update backup, dedicated Nginx host, Let's Encrypt and public HTTPS health verification. Does not replace other domain vhosts.

## Explicit implementation boundaries

This is a tested core marketplace, **not the entire requested enterprise inventory**. No live payments, escrow, refunds, payouts, wallets, financing, subscriptions, tax calculation or buyer-protection guarantee. Commission and membership values are stored configuration, not billing. Dispute approval does not move money. The API refuses enabling live payments.

Not yet implemented: visual search and full media galleries; tiered prices and structured variants; shipping rate APIs and live carrier tracking; external KYC; translated messaging and localization; SMS/email/push delivery and email verification; self-service email reset; custom supplier storefront layout editor; ad delivery and attribution; coupons; bulk catalog import; customer CRM; live analytics; granular custom permissions and staff revocation GUI; native iOS and Google Play distribution; durable job queues, external search index, accounting ledger, automated DNS, and account-owned panel inventory registration (a verified Hosting Domains snapshot integration is now included). These require further implementation, provider contracts/credentials, and operational testing. No placeholder button claims these services ran.

Private tenant records are visible to all members of that tenant; granular departmental scopes are not implemented. RFQs/jobs/products are intentionally public only when published. Platform super admins can access all records and their actions are audited. SQLite WAL with serialized writes fits a small single-server deployment; do not claim enterprise scale or multi-node readiness.

## Local verification

Python 3.11+ and Node 18+ (syntax checking only). No Python packages are needed for local tests:

```sh
python -m unittest discover -s tests -v
node --check static/app.js
python app.py init
ABH_SECURE_COOKIE=0 python app.py serve
```

Open `http://127.0.0.1:8097`. Disable secure cookies only on local loopback development. No demo users/passwords are created in local development. Registration requires Terms agreement and Privacy acknowledgment. The built-in server is for local development only.

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

The deployment automatically selects a free loopback port in **18770–18869** and preserves it in `/var/lib/afribulkhub/listen-port.json`. It reuses a healthy existing Africa Bulk Hub listener and never stops or takes over another application. Set `-e hub_port=PORT` to require a particular port; an occupied foreign port fails explicitly. The dedicated domain proxy follows the selected port while retaining TLS settings. It requires DNS pointing to the server and public ports 80/443 for certificate issuance. `www` is not provisioned; add it intentionally with matching DNS/certificate/vhost configuration if required. Existing dedicated vhosts are retained to preserve Certbot edits. On first install, inspect for duplicate `server_name afribulkhub.com` declarations in other Nginx vhosts before deploying.

By default the playbook creates one initial super administrator only when none exists. Its generated credentials are root-only at `/var/lib/afribulkhub-bootstrap/initial-admin.json`; existing administrators and passwords are preserved. Set `-e hub_bootstrap_admin=false` to manage this manually. Manual creation:

```sh
sudo -u afribulkhub env ABH_DATABASE=/var/lib/afribulkhub/hub.db /opt/afribulkhub/venv/bin/python /opt/afribulkhub/app.py admin --email YOUR_REAL_EMAIL
```

Sign in at `https://afribulkhub.com` and open **Dashboard → Platform operations**. There is no default admin password. The Ansible installation never sends a password through command arguments.

### Olamidepanel GUI inventory

Register `afribulkhub.com` under the correct hosting account using the existing Olamidepanel Hosting Domains GUI. After trusted HTTPS verification, the playbook merges this deployment into the existing `/var/lib/olamidepanel/hosted-domains.json` Hosting Domains snapshot, preserving unrelated entries. It does not guess a hosting account ID or alter MySQL account-owned domains. Service metadata is written to `/var/lib/afribulkhub/hosting-status.json`. Absent panel data/group is reported as skipped; malformed existing snapshots cause failure instead of replacement.

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

## Branding, legal pages, Android APK and one-command publication

Slogan: **Connecting Africa. Trading Beyond.** The approved logo/emblem appears in website navigation, hero/background, legal pages, Android launcher and store artwork. The native Android website client is built and signed; see [mobile details](mobile/README.md). Download it from `/#download` after website deployment, or directly from `static/downloads/africa-bulk-hub.apk` in this repository. `/terms`, `/privacy`, and `/copyright` are public server routes; registration records acceptance versions. See [operator legal notes](LEGAL_NOTES.md).

On the existing Debian Olamidepanel host, with DNS pointing afribulkhub.com to that server:

```sh
sudo apt-get update
sudo apt-get install -y git ansible
sudo ansible-pull -U https://github.com/olamidebello/afribulkhub.com.git -C main -i localhost, -d /opt/afribulkhub-source deploy/pull-and-deploy.yml
```

This pulls the source, deploys the service, verifies HTTPS/legal pages/APK, provisions the first administrator if needed, merges the verified panel snapshot, and updates the **existing** African Apps Store service with the APK and branded Hosted apps listing. Default certificate/admin email is `dobcalldemo@gmail.com`; override `hub_email` if needed. Existing source modifications are not discarded. The Apps Store must already be installed. Use `-e hub_publish_store=false` to deploy only the website. DNS registrar credentials and live hosting access are not embedded.

The paired store playbook is `olamidebello/africanappsstore:ansible/deploy-afribulkhub-mobile.yml`. The future public store link is `https://africanappsstore.space/#Hosted%20apps`; its APK path is `/downloads/africa-bulk-hub.apk`. Repository publication is separate from running these playbooks on the live host. No live deployment, DNS, certificate or Android device runtime success is inferred from the local build.

Validation for this release: 19 website/backend integration tests and two Apps Store release tests passed. APK signature v2/v3, package/version, ZIP structure, alignment and SHA-256 were checked. JavaScript and Python syntax checks passed; deployment YAML parsed locally. Live Ansible execution, public URLs and Android device behavior remain unverified.

### Recovery from the Africa Atona port conflict

Port 8097 is occupied by Africa Atona on the supplied server. Deployment now defaults to `hub_port=0` (automatic selection), persists its own port, and uses that same value in Gunicorn, the dedicated Nginx vhost and the panel snapshot. Rerun the original `ansible-pull` command to recover. Existing administrators and application data are preserved. The failed initial attempt stopped before creating its Nginx host; no Atona restart or configuration change is needed.
