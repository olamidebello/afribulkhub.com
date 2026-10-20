import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_app import MarketplaceTests as Fixture,Client
class LanguageTests(unittest.TestCase):
    setUp=Fixture.setUp
    tearDown=Fixture.tearDown
    def test_catalog_has_unique_codes_and_pidgin_default(self):
        root=Path(__file__).resolve().parents[1]
        data=json.loads((root/'static/i18n/languages.json').read_text());self.assertEqual(data['default'],'pcm');codes=[r['code'] for r in data['languages']];self.assertEqual(len(codes),len(set(codes)));self.assertGreater(len(codes),6000)
        for code in ['pcm','en','yo','ha','ig','sw','zu','am','ar']:self.assertIn(code,codes)
        rows={r['code']:r for r in data['languages']};self.assertEqual(rows['pcm']['ui'],'available');self.assertEqual(rows['yo']['ui'],'fallback')
        dictionary=json.loads((root/'static/i18n/pcm.json').read_text());self.assertEqual(dictionary['Source products'],'Find products')
    def test_preferences_are_per_user_persisted_and_csrf_protected(self):
        self.assertEqual(self.buyer.req('/api/language')[1]['language'],'pcm')
        self.assertEqual(self.buyer.req('/api/language','PATCH',{'language':'yo'},csrf=False)[0],403)
        self.assertEqual(self.buyer.req('/api/language','PATCH',{'language':'yo'})[0],200)
        self.assertEqual(self.outsider.req('/api/language')[1]['language'],'pcm')
        self.assertEqual(self.buyer.req('/api/session')[1]['user']['language'],'yo')
        client=Client();code,result=client.req('/api/login','POST',{'email':'buyer@test.com','password':'a-secure-password!'})
        self.assertEqual(code,200);self.assertEqual(result['user']['language'],'yo')
        self.assertEqual(client.req('/api/language','PATCH',{'language':'not-a-real-language'})[0],400)
        self.assertEqual(client.req('/api/language')[1]['language'],'yo')
if __name__=='__main__':unittest.main()

# unittest discovery must not duplicate cases from the fixture module.
del Fixture
