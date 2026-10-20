import base64,hashlib,io,json,os,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app

class ReleaseTests(unittest.TestCase):
    def request(self,path,method='GET',data=None):
        body=json.dumps(data or {}).encode();status=[];headers=[]
        env={'REQUEST_METHOD':method,'PATH_INFO':path,'QUERY_STRING':'','CONTENT_LENGTH':str(len(body)),'wsgi.input':io.BytesIO(body),'HTTP_HOST':'localhost','REMOTE_ADDR':'127.0.0.49'}
        def start(s,h):status.append(int(s.split()[0]));headers.extend(h)
        content=b''.join(app.application(env,start));return status[0],dict(headers),content
    def test_legal_routes_and_mobile_download(self):
        for path,marker in [('/terms',b'Terms and Conditions'),('/privacy',b'Privacy Policy'),('/copyright',b'Copyright')]:
            code,headers,body=self.request(path);self.assertEqual(code,200);self.assertIn(marker,body);self.assertIn(b'dobcalldemo@gmail.com',body)
        code,headers,body=self.request('/downloads/africa-bulk-hub.apk','HEAD');self.assertEqual(code,200);self.assertEqual(body,b'');self.assertGreater(int(headers['Content-Length']),1000)
        code,headers,body=self.request('/downloads/africa-bulk-hub.apk');self.assertEqual(code,200)
        release=json.loads((app.ROOT/'static/downloads/release.json').read_text());self.assertEqual(hashlib.sha256(body).hexdigest(),release['sha256'])
        with zipfile.ZipFile(io.BytesIO(body)) as z:self.assertTrue({'AndroidManifest.xml','classes.dex'}.issubset(z.namelist()))
    def test_registration_requires_and_records_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            old=app.DB;app.DB=str(Path(directory)/'acceptance.db');app.init_db()
            try:
                data={'email':'legal@example.com','password':'a-secure-password!','name':'Legal','company':'Legal Co','role':'buyer'}
                self.assertEqual(self.request('/api/register','POST',data)[0],400)
                data['accept_terms']=True;self.assertEqual(self.request('/api/register','POST',data)[0],200)
                with app.connect() as c:
                    row=c.execute('SELECT * FROM acceptances').fetchone();self.assertEqual(row['terms_version'],'2026-10-20');self.assertEqual(row['privacy_version'],'2026-10-20')
            finally:app.DB=old
