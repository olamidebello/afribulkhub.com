# African language catalog and translation status

Default interface: Nigerian Pidgin (`pcm`, Naijá). English (`en`) is the fallback. This release provides a manually authored Pidgin dictionary for core marketplace screens, forms, actions and navigation. It does **not** claim that every label, server error, legal page or native Android control is translated.

The searchable catalog contains 6,577 entries from Glottolog's African language/dialect records, supplemented by Unicode CLDR territory-language entries through Babel 2.17.0. Families are excluded. Language and dialect distinctions, historical entries and country coverage reflect these source datasets; no finite catalog is a guarantee that every community's name or variety is represented. A catalog entry is not a translated-interface claim. Untranslated selections use English and display that fact. Original business records, product names, messages and legal texts are not automatically translated.

## Attribution and changes

Glottolog CLDF contributors: https://github.com/glottolog/glottolog-cldf . Source: `cldf/languages.csv`, Git blob `774cbd8cb1bbdbc2eab64edf5df552b61252e876`. Licensed CC BY 4.0; full license is provided in `GLOTTOLOG-LICENSE.txt`. Changes: filter to African macroarea or African countries/territories, exclude family nodes, retain language/dialect names and codes, normalize code aliases, merge country metadata and supplement from CLDR. Glottolog identifiers remain attached for traceability.

Unicode CLDR: https://cldr.unicode.org/ . Babel 2.17.0: https://babel.pocoo.org/ . Only generated language-name/territory data is used at runtime; Babel is not a server dependency. Babel's included license is reproduced in `BABEL-LICENSE.txt`; the CLDR Unicode license is in `UNICODE-LICENSE.txt`. Source record and transformation metadata are in `languages.json`.

Browser language preference uses localStorage (`abh-language`). Signed-in choices are stored per user and restored on another login/device. No external translation provider, machine translation, outbound data transfer or native JavaScript bridge has been added. Legal pages remain their English originals.
