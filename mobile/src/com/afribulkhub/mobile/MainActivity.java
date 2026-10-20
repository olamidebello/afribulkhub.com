package com.afribulkhub.mobile;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.JsResult;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.PopupMenu;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

/** Dedicated HTTPS website client. No JavaScript/native bridge or tracking SDK. */
public class MainActivity extends Activity {
    private static final String HOME="https://afribulkhub.com/";
    private static final int CHOOSE_FILE=127;
    private WebView web;
    private TextView problem;
    private ValueCallback<Uri[]> fileCallback;
    private final int green=Color.rgb(20,65,46);
    private int dp(int n){ return (int)(n*getResources().getDisplayMetrics().density); }
    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(Color.rgb(247,248,243));
        root.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());return insets.consumeSystemWindowInsets();});
        LinearLayout brand=new LinearLayout(this);brand.setGravity(Gravity.CENTER_VERTICAL);brand.setPadding(dp(12),dp(6),dp(12),dp(6));
        ImageView icon=new ImageView(this);icon.setImageResource(com.afribulkhub.mobile.R.drawable.hub_icon);icon.setContentDescription("Africa Bulk Hub logo");brand.addView(icon,new LinearLayout.LayoutParams(dp(52),dp(52)));
        TextView title=new TextView(this);title.setText("Africa Bulk Hub\nConnecting Africa. Trading Beyond.");title.setTextSize(14);title.setTextColor(green);brand.addView(title);root.addView(brand);
        ProgressBar progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);root.addView(progress,new LinearLayout.LayoutParams(-1,dp(3)));
        FrameLayout content=new FrameLayout(this);root.addView(content,new LinearLayout.LayoutParams(-1,0,1));
        web=new WebView(this);content.addView(web,new FrameLayout.LayoutParams(-1,-1));
        problem=new TextView(this);problem.setText("The marketplace could not be reached. Check your internet connection, then tap Reload or Browser.");problem.setTextColor(green);problem.setGravity(Gravity.CENTER);problem.setPadding(dp(28),dp(28),dp(28),dp(28));problem.setBackgroundColor(Color.rgb(247,248,243));problem.setVisibility(View.GONE);content.addView(problem,new FrameLayout.LayoutParams(-1,-1));
        WebSettings settings=web.getSettings();settings.setJavaScriptEnabled(true);settings.setDomStorageEnabled(true);settings.setAllowFileAccess(false);settings.setAllowContentAccess(false);settings.setAllowFileAccessFromFileURLs(false);settings.setAllowUniversalAccessFromFileURLs(false);settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);settings.setSafeBrowsingEnabled(true);settings.setUserAgentString(settings.getUserAgentString()+" AfricaBulkHub/1.0.0");
        CookieManager.getInstance().setAcceptCookie(true);CookieManager.getInstance().setAcceptThirdPartyCookies(web,false);
        web.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView v,WebResourceRequest request){Uri uri=request.getUrl();if(isOurSite(uri))return false;if(request.isForMainFrame())openExternal(uri);return true;}
            @Override public void onPageFinished(WebView v,String url){CookieManager.getInstance().flush();}
            @Override public void onReceivedError(WebView v,WebResourceRequest req,WebResourceError err){if(req.isForMainFrame())problem.setVisibility(View.VISIBLE);}
            @Override public void onPageStarted(WebView v,String url,android.graphics.Bitmap bitmap){problem.setVisibility(View.GONE);}
        });
        web.setWebChromeClient(new WebChromeClient(){
            @Override public void onProgressChanged(WebView v,int value){progress.setProgress(value);progress.setVisibility(value==100?View.GONE:View.VISIBLE);}
            @Override public boolean onJsConfirm(WebView v,String url,String message,JsResult result){new AlertDialog.Builder(MainActivity.this).setMessage(message).setPositiveButton("Continue",(d,w)->result.confirm()).setNegativeButton("Cancel",(d,w)->result.cancel()).setOnCancelListener(d->result.cancel()).show();return true;}
            @Override public boolean onShowFileChooser(WebView v,ValueCallback<Uri[]> callback,FileChooserParams params){
                if(fileCallback!=null)fileCallback.onReceiveValue(null);fileCallback=callback;
                Intent choose=new Intent(Intent.ACTION_OPEN_DOCUMENT);choose.addCategory(Intent.CATEGORY_OPENABLE);choose.setType("*/*");choose.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"application/pdf","image/png","image/jpeg"});
                try{startActivityForResult(choose,CHOOSE_FILE);}catch(Exception e){fileCallback.onReceiveValue(null);fileCallback=null;Toast.makeText(MainActivity.this,"Open Browser to upload files.",Toast.LENGTH_LONG).show();}return true;
            }
        });
        web.setDownloadListener((url,agent,disposition,type,length)->{if(url.startsWith("https://"))openExternal(Uri.parse(url));else Toast.makeText(this,"Use Browser to download evidence files and CSV exports.",Toast.LENGTH_LONG).show();});
        LinearLayout controls=new LinearLayout(this);controls.setPadding(dp(4),dp(4),dp(4),dp(4));
        addButton(controls,"Home",v->web.loadUrl(HOME));addButton(controls,"Reload",v->web.reload());addButton(controls,"Browser",v->openExternal(Uri.parse(web.getUrl()!=null&&isOurSite(Uri.parse(web.getUrl()))?web.getUrl():HOME)));
        addButton(controls,"Info",v->{PopupMenu menu=new PopupMenu(this,v);for(String name:new String[]{"Terms","Privacy","Copyright","About"})menu.getMenu().add(name);menu.setOnMenuItemClickListener(item->{String label=item.getTitle().toString();if(label.equals("About"))new AlertDialog.Builder(this).setTitle("Africa Bulk Hub 1.0.0").setMessage("Connecting Africa. Trading Beyond.\nDedicated website client. Internet required. No native push notifications or offline trading. Use Browser for unsupported downloads.\n© 2026 Africa Bulk Hub").setPositiveButton("Close",null).show();else web.loadUrl(HOME+label.toLowerCase(java.util.Locale.ROOT));return true;});menu.show();});root.addView(controls);
        setContentView(root);root.requestApplyInsets();
        if(state==null)web.loadUrl(HOME);else web.restoreState(state);
    }
    private boolean isOurSite(Uri uri){return "https".equalsIgnoreCase(uri.getScheme())&&"afribulkhub.com".equalsIgnoreCase(uri.getHost())&&(uri.getPort()==-1||uri.getPort()==443);}
    private void addButton(LinearLayout root,String text,View.OnClickListener listener){Button b=new Button(this);b.setText(text);b.setTextSize(11);b.setTextColor(green);b.setAllCaps(false);b.setOnClickListener(listener);root.addView(b,new LinearLayout.LayoutParams(0,dp(48),1));}
    private void openExternal(Uri uri){String scheme=uri.getScheme();if(!"https".equalsIgnoreCase(scheme)&&!"mailto".equalsIgnoreCase(scheme)){Toast.makeText(this,"Unsupported link. Use your browser if needed.",Toast.LENGTH_SHORT).show();return;}try{startActivity(new Intent(Intent.ACTION_VIEW,uri));}catch(Exception e){Toast.makeText(this,"No browser is available.",Toast.LENGTH_SHORT).show();}}
    @Override protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);if(request==CHOOSE_FILE&&fileCallback!=null){Uri uri=result==RESULT_OK&&data!=null?data.getData():null;String type=uri!=null?getContentResolver().getType(uri):null;boolean valid=uri!=null&&"content".equals(uri.getScheme())&&("application/pdf".equals(type)||"image/png".equals(type)||"image/jpeg".equals(type));fileCallback.onReceiveValue(valid?new Uri[]{uri}:null);fileCallback=null;}}
    @Override protected void onSaveInstanceState(Bundle state){web.saveState(state);super.onSaveInstanceState(state);}
    @Override public void onBackPressed(){if(web.canGoBack())web.goBack();else super.onBackPressed();}
    @Override protected void onPause(){CookieManager.getInstance().flush();web.onPause();super.onPause();}
    @Override protected void onResume(){super.onResume();if(web!=null)web.onResume();}
    @Override protected void onDestroy(){if(fileCallback!=null)fileCallback.onReceiveValue(null);if(web!=null){web.stopLoading();web.destroy();}super.onDestroy();}
}
