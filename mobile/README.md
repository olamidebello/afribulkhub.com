# Africa Bulk Hub Android client

Package: `com.afribulkhub.mobile`. Version `1.0.0`, version code `1`. Minimum Android 8 (API 26), target API 35. Dedicated HTTPS WebView client; no native replica of every backend module. The app needs internet and a working afribulkhub.com deployment. It includes native Home, Reload, Browser, legal/About navigation, first-party session storage, an explicit document picker for PDF/PNG/JPEG, restricted in-app origin navigation, safe browsing and no native JavaScript bridge. Blob-based evidence/CSV downloads may require the Browser control. No native push, offline trading or external payment processing is included. No broad storage, contacts, camera, microphone or location permission is requested.

The compiled APK, package/version, alignment, and APK Signature Schemes v2/v3 were verified with Android SDK 35 tools. No Android emulator or physical-device runtime test was performed here. File selection and WebView behavior still require device acceptance testing.

## Rebuild

Install a JRE 17+, Android SDK platform 35 and build-tools 35.0.0, and the Eclipse ECJ compiler. Set paths for the SDK, ECJ jar and **the existing private publisher key**. Passwords go through environment variables, not command-line arguments:

```sh
export ANDROID_SDK_ROOT=/path/to/android-sdk
export ECJ_JAR=/path/to/ecj.jar
export ABH_KEYSTORE=/secure/path/afribulkhub.jks
read -rsp 'Signing password: ' ABH_SIGNING_PASSWORD
export ABH_SIGNING_PASSWORD
python3 mobile/build.py
unset ABH_SIGNING_PASSWORD
```

Outputs are `static/downloads/africa-bulk-hub.apk`, its `.sha256`, and `release.json`. The build does not generate or replace signing keys. The same key must be preserved for compatible Android updates. The publisher certificate SHA-256 is `c1b4ffa9f9b30913b0e6fe47e13452e885795eec6adc1e8c109f60321c5c746c`. Private key material is not in either repository.

When updating versions, update manifest, native About/user agent, build metadata validation and store catalog together. Regenerate the checksum and test before publishing. This direct APK is not a Google Play submission.

Security reference: https://developer.android.com/privacy-and-security/risks/webview-unsafe-file-inclusion
