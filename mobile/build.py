#!/usr/bin/env python3
"""Build and verify the Android APK with SDK tools and ECJ, without Gradle downloads.
Requires ANDROID_SDK_ROOT, ECJ_JAR, ABH_KEYSTORE, ABH_SIGNING_PASSWORD.
A persistent private keystore is required; this script never generates/overwrites keys.
"""
import hashlib,json,os,shutil,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];MOBILE=ROOT/'mobile'
def run(*cmd):subprocess.run([str(c) for c in cmd],check=True)
def main():
 sdk=Path(os.environ['ANDROID_SDK_ROOT']);ecj=Path(os.environ['ECJ_JAR']);key=Path(os.environ['ABH_KEYSTORE'])
 if not key.is_file() or not os.environ.get('ABH_SIGNING_PASSWORD'):raise SystemExit('Set a private persistent keystore and password in the environment')
 version=os.environ.get('ABH_BUILD_TOOLS','35.0.0');tools=sdk/'build-tools'/version;android=sdk/'platforms'/'android-35'/'android.jar'
 for path in (ecj,android,tools/'aapt',tools/'d8',tools/'zipalign',tools/'apksigner'):
  if not path.exists():raise SystemExit('Missing build dependency: '+str(path))
 build=MOBILE/'build';shutil.rmtree(build,ignore_errors=True);build.mkdir()
 for name in ('generated','classes','dex'):(build/name).mkdir()
 base=build/'resources.apk'
 run(tools/'aapt','package','-f','-M',MOBILE/'AndroidManifest.xml','-S',MOBILE/'res','-I',android,'-J',build/'generated','-F',base)
 sources=list((MOBILE/'src').rglob('*.java'))+list((build/'generated').rglob('*.java'))
 run('java','-jar',ecj,'-source','1.8','-target','1.8','-bootclasspath',str(android)+os.pathsep+str(tools/'core-lambda-stubs.jar'),'-d',build/'classes',*sources)
 run(tools/'d8','--min-api','26','--lib',android,'--output',build/'dex',*list((build/'classes').rglob('*.class')))
 unsigned=build/'unsigned.apk';shutil.copyfile(base,unsigned)
 with zipfile.ZipFile(unsigned,'a',compression=zipfile.ZIP_DEFLATED) as z:z.write(build/'dex'/'classes.dex','classes.dex')
 aligned=build/'aligned.apk';run(tools/'zipalign','-f','4',unsigned,aligned)
 out=ROOT/'static'/'downloads';out.mkdir(exist_ok=True);apk=out/'africa-bulk-hub.apk'
 run(tools/'apksigner','sign','--ks',key,'--ks-key-alias','afribulkhub','--ks-pass','env:ABH_SIGNING_PASSWORD','--key-pass','env:ABH_SIGNING_PASSWORD','--v4-signing-enabled','false','--out',apk,aligned)
 run(tools/'apksigner','verify','--verbose','--print-certs',apk);run(tools/'zipalign','-c','4',apk)
 badging=subprocess.check_output([str(tools/'aapt'),'dump','badging',str(apk)],text=True)
 if "package: name='com.afribulkhub.mobile' versionCode='1' versionName='1.0.0'" not in badging:raise SystemExit('Unexpected package or version')
 digest=hashlib.sha256(apk.read_bytes()).hexdigest();(out/'africa-bulk-hub.apk.sha256').write_text(digest+'  africa-bulk-hub.apk\n')
 metadata={'name':'Africa Bulk Hub','slogan':'Connecting Africa. Trading Beyond.','package':'com.afribulkhub.mobile','version':'1.0.0','version_code':1,'min_android':'8.0','category':'Business','website':'https://afribulkhub.com/','privacy':'https://afribulkhub.com/privacy','terms':'https://afribulkhub.com/terms','copyright':'https://afribulkhub.com/copyright','channel':'direct','status':'built_hosting_pending','description':'Africa Bulk Hub dedicated HTTPS marketplace client. Source wholesale products, manage RFQs and orders, and connect for service work. Internet and an operational website required. No offline trading or native push notifications. Use Browser for unsupported downloads.','apk_url':'https://africanappsstore.space/downloads/africa-bulk-hub.apk','website_apk_url':'https://afribulkhub.com/downloads/africa-bulk-hub.apk','sha256':digest,'size_bytes':apk.stat().st_size,'signing':'Persistent private publisher key; no private signing material in repository'}
 (out/'release.json').write_text(json.dumps(metadata,indent=2)+'\n');print('Verified build:',apk,'SHA-256',digest)
if __name__=='__main__':main()
