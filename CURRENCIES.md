# Currency support

**Default for new prices: Nigerian naira (NGN, ₦).** The catalog includes 46 current ISO-coded currencies used in African countries and territories, including shared and international currencies, plus the proposed custom unit Afira. Regional currency and territory names come from Unicode CLDR through Babel 2.17.0; associated licenses are in `static/i18n/`. The catalog records its date and sources. It is not a list of every informal, historical or cryptocurrency unit.

## Afira

- Name: Afira
- Proposed symbol: **Ⱥ**
- Proposed code: **AFR** (custom application code, not represented as an ISO assignment)
- Pronunciation: **Ah-FEE-rah**
- Subdivision: **1 Afira = 100 cents**
- Example prices: **Ⱥ10 · Ⱥ250 · Ⱥ1,000**

The name combines Africa with a new era, representing shared prosperity across the continent. The symbol’s strong A shape connects it to Africa.

Afira is a proposed custom pricing unit. Listing it does not issue money or a redeemable balance, represent official legal tender, assign an exchange value, promise backing, or activate payment acceptance. There is no exchange-rate feed, conversion, wallet, escrow or redemption service. The currency guide and AFR pricing surfaces disclose this status. Parties must separately agree any lawful settlement arrangement. NGN remains the default.

## Records and preferences

The top-bar selector sets the default for **new** monetary entries. Browser choice is stored locally; signed-in choice is stored per user and restored on login. Product, RFQ, job, campaign, quotation and work-application forms provide explicit currency fields. Orders inherit their product or accepted quotation currency; disputes inherit the order currency. Clients cannot override these snapshots by submitting another code.

Changing a preference does not convert displayed prices. Each record retains its currency, and the cart shows separate subtotals by currency. A saved priced listing/request cannot have its unit silently replaced; create a new one when changing denomination. Catalog inclusion does not mean a payment method is available. Existing supplier membership configuration named `seller_monthly_usd` remains explicitly denominated in USD; it is not silently converted into a naira fee.

Prices are checked against the currency's minor-unit precision; totals use decimal arithmetic and half-up rounding. BIF, DJF, GNF, KMF, RWF, UGX, XAF and XOF use zero decimal places; LYD/TND use three; the remaining catalog entries, including AFR/NGN, use two. The backend records the unit explicitly.

## Safe upgrade

Before this release, the site used USD for all prices, including records without a stored currency field. A transactional one-time migration labels such existing monetary records **USD**, preserving their numeric amounts, and leaves already explicit codes unchanged. New entries default to NGN. Repeated initialization does not change existing prices. The regular deployment takes its pre-update database backup and initializes the additive tables/migration. Port selection and existing admin credentials are preserved.

The Android website client receives these changes from the hosted site; no signed APK replacement is required. The native app's controls are unchanged.

Sources: https://cldr.unicode.org/ ; https://www.iso.org/iso-4217-currency-codes.html ; Zimbabwe code reference: https://www.rbz.co.zw/index.php/publications-notices/notices/press-release/1419-press-statement-introduction-of-zimbabwe-gold-zig-currency-code-zwg .
