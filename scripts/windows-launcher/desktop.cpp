#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <dwmapi.h>
#include <shellapi.h>
#include <windowsx.h>
#include <commctrl.h>
#include <commdlg.h>
#include <wrl.h>
#include <gdiplus.h>
#include <filesystem>
#include <fstream>
#include <string>
#include "webview2/WebView2.h"
using Microsoft::WRL::Callback;
using Microsoft::WRL::ComPtr;
static HWND window;
static std::wstring root,readyFile,url;
static HANDLE preparation,backend,stopProcess;
static ComPtr<ICoreWebView2Controller> controller;
static ComPtr<ICoreWebView2> view;
static bool closing=false,environmentStarted=false;
static bool darkTheme=true,pinned=false,keyboardEditing=false;
static HWND pinButton,captionButtons[5],dockTab;
static bool docked=false,dockExpanded=false,dockWasPinned=false;
static int dockSide=0;
static RECT undockedBounds={},dockOpenBounds={},dockClosedBounds={};
static HWND chromeTips;
static bool tabDragging=false,tabPulled=false;static POINT tabStart={};
static void Layout();
static void PositionDockTab();
static ULONG_PTR tabGdiToken=0;
static bool moduleWindow=false;static std::wstring moduleName,serverPort=L"18533",exePath;static DWORD sharedBackend=0;
static void PortableEnvironment(){
 struct Location{const wchar_t* name;const wchar_t* folder;};
 const Location paths[]={{L"TEMP",L"\\tmp"},{L"TMP",L"\\tmp"},{L"TMPDIR",L"\\tmp"},{L"LOCALAPPDATA",L"\\state\\local"},{L"APPDATA",L"\\state\\roaming"},{L"USERPROFILE",L"\\state\\home"},{L"HOME",L"\\state\\home"},{L"ANDROID_USER_HOME",L"\\state\\android"}};
 for(const auto& p:paths){std::wstring value=root+p.folder;std::filesystem::create_directories(value);SetEnvironmentVariableW(p.name,value.c_str());}
 SetEnvironmentVariableW(L"ADB_VENDOR_KEYS",(root+L"\\state\\android\\adbkey").c_str());
 SetEnvironmentVariableW(L"PYTHONDONTWRITEBYTECODE",L"1");
 SetEnvironmentVariableW(L"WEBVIEW2_USER_DATA_FOLDER",(root+L"\\state\\webview").c_str());
}
static DWORD OverlayStyle(){return WS_EX_TOPMOST|WS_EX_NOACTIVATE|(moduleWindow?WS_EX_TOOLWINDOW:WS_EX_APPWINDOW);}
static void NotifyOverlay(){if(view)view->ExecuteScript(pinned?(keyboardEditing?L"window.miOverlayState&&window.miOverlayState(true,true)":L"window.miOverlayState&&window.miOverlayState(true,false)"):L"window.miOverlayState&&window.miOverlayState(false,false)",nullptr);}
static void KeyboardEditing(bool enabled){
 if(!pinned||keyboardEditing==enabled)return;keyboardEditing=enabled;
 LONG_PTR style=GetWindowLongPtrW(window,GWL_EXSTYLE);
 SetWindowLongPtrW(window,GWL_EXSTYLE,enabled?style&~static_cast<LONG_PTR>(WS_EX_NOACTIVATE):style|WS_EX_NOACTIVATE);
 if(enabled){SetForegroundWindow(window);if(controller)controller->MoveFocus(COREWEBVIEW2_MOVE_FOCUS_REASON_PROGRAMMATIC);if(view)view->ExecuteScript(L"window.miRestoreInputFocus&&window.miRestoreInputFocus()",nullptr);}
 NotifyOverlay();
}
static int ResizeBorder(){return IsZoomed(window)?0:MulDiv(6,GetDpiForWindow(window),96);}
static int CaptionHeight(){return MulDiv(22,GetDpiForWindow(window),96);}
static int TabSize(){return MulDiv(30,GetDpiForWindow(window),96);}
static int TabLength(){return MulDiv(108,GetDpiForWindow(window),96);}
static COLORREF ChromeBackground(){return darkTheme?RGB(18,18,18):RGB(246,246,246);}
static RECT PaperRect(){
 RECT r;GetClientRect(window,&r);if(docked&&!dockExpanded)return RECT{};
 int side=docked?dockSide:1,t=IsZoomed(window)?0:TabSize();
 if(side==1)r.right-=t;else r.left+=t;return r;
}
static RECT TabRect(){
 RECT r;GetClientRect(window,&r);if(docked&&!dockExpanded)return r;
 RECT paper=PaperRect();int side=docked?dockSide:1,t=TabSize(),longer=TabLength();
 int y=(r.bottom-longer)/2;return side==1?RECT{paper.right-1,y,r.right,y+longer}:RECT{0,y,paper.left+1,y+longer};
}
// Two symmetric cubic shoulders have zero curvature at the paper/outer
// straight edges and at their shared inflection: a continuous G2 silhouette.
static void TabPath(Gdiplus::GraphicsPath& path,float width,float height,bool right){
 float w=width-1,h=height-1,shoulder=min(h*.29f,w*1.05f),a=shoulder*.20f;
 path.StartFigure();path.AddBezier(0.f,0.f,0.f,a,0.f,a,w/2,shoulder/2);
 path.AddBezier(w/2,shoulder/2,w,shoulder-a,w,shoulder-a,w,shoulder);
 path.AddLine(w,shoulder,w,h-shoulder);
 path.AddBezier(w,h-shoulder,w,h-shoulder+a,w,h-shoulder+a,w/2,h-shoulder/2);
 path.AddBezier(w/2,h-shoulder/2,0.f,h-a,0.f,h-a,0.f,h);path.CloseFigure();
 if(right){Gdiplus::Matrix mirror(-1,0,0,1,w,0);path.Transform(&mirror);}
}
static HBITMAP TabBitmap(int width,int height,int dpi,int side,bool dark,void** output=nullptr){
 BITMAPINFO info={};info.bmiHeader={sizeof(BITMAPINFOHEADER),width,-height,1,32,BI_RGB};void* pixels=nullptr;
 HBITMAP bitmap=CreateDIBSection(nullptr,&info,DIB_RGB_COLORS,&pixels,nullptr,0);if(!bitmap)return nullptr;
 Gdiplus::Bitmap surface(width,height,width*4,PixelFormat32bppPARGB,static_cast<BYTE*>(pixels));
 Gdiplus::Graphics graphics(&surface);graphics.Clear(Gdiplus::Color(0,0,0,0));graphics.SetSmoothingMode(Gdiplus::SmoothingModeAntiAlias);graphics.SetPixelOffsetMode(Gdiplus::PixelOffsetModeHalf);
 Gdiplus::GraphicsPath path;TabPath(path,float(width),float(height),side==2);BYTE shade=dark?18:246;
 Gdiplus::SolidBrush fill(Gdiplus::Color(255,shade,shade,shade));graphics.FillPath(&fill,&path);
 graphics.SetTextRenderingHint(Gdiplus::TextRenderingHintAntiAliasGridFit);Gdiplus::FontFamily family(L"Segoe UI");Gdiplus::Font font(&family,11.f*dpi/96,Gdiplus::FontStyleBold,Gdiplus::UnitPixel);
 Gdiplus::StringFormat format;format.SetAlignment(Gdiplus::StringAlignmentCenter);format.SetLineAlignment(Gdiplus::StringAlignmentCenter);
 BYTE ink=dark?220:35;Gdiplus::SolidBrush text(Gdiplus::Color(255,ink,ink,ink));float pitch=14.f*dpi/96,top=(height-3*pitch)/2;const wchar_t label[]=L"HDR";
 for(int i=0;i<3;i++)graphics.DrawString(label+i,1,&font,Gdiplus::RectF(0,top+i*pitch,float(width),pitch),&format,&text);
 graphics.Flush(Gdiplus::FlushIntentionSync);if(output)*output=pixels;return bitmap;
}
static void PositionDockTab(){
 if(!dockTab)return;if(IsZoomed(window)||IsIconic(window)||!IsWindowVisible(window)){ShowWindow(dockTab,SW_HIDE);return;}
 RECT tab=TabRect();POINT position={tab.left,tab.top};ClientToScreen(window,&position);int width=tab.right-tab.left,height=tab.bottom-tab.top,side=docked?dockSide:1,dpi=GetDpiForWindow(window);
 SetWindowPos(dockTab,pinned?HWND_TOPMOST:HWND_NOTOPMOST,position.x,position.y,width,height,SWP_NOACTIVATE|SWP_NOOWNERZORDER);
 static int oldWidth=0,oldHeight=0,oldSide=0,oldDpi=0;static bool oldDark=false;
 if(width!=oldWidth||height!=oldHeight||side!=oldSide||dpi!=oldDpi||darkTheme!=oldDark){
  HBITMAP bitmap=TabBitmap(width,height,dpi,side,darkTheme);if(!bitmap)return;
  HDC dc=CreateCompatibleDC(nullptr);auto old=SelectObject(dc,bitmap);POINT origin={};SIZE size={width,height};BLENDFUNCTION blend={AC_SRC_OVER,0,255,AC_SRC_ALPHA};
  BOOL rendered=UpdateLayeredWindow(dockTab,nullptr,&position,&size,dc,&origin,0,&blend,ULW_ALPHA);SelectObject(dc,old);DeleteDC(dc);DeleteObject(bitmap);if(!rendered)return;
  oldWidth=width;oldHeight=height;oldSide=side;oldDpi=dpi;oldDark=darkTheme;
 }
 ShowWindow(dockTab,SW_SHOWNOACTIVATE);
}
static void RoundWindow(HWND hwnd,int side=0){
 static RECT previous={};static int mode=-1;RECT r;GetClientRect(hwnd,&r);int key=(IsZoomed(hwnd)?100:0)+(docked?dockSide*2+int(dockExpanded):0);
 if(EqualRect(&r,&previous)&&mode==key)return;previous=r;mode=key;
 if(IsZoomed(hwnd)){SetWindowRgn(hwnd,nullptr,TRUE);return;}
 int z=MulDiv(16,GetDpiForWindow(hwnd),96);RECT paper=PaperRect();
 HRGN region=IsRectEmpty(&paper)?CreateRectRgn(0,0,0,0):CreateRoundRectRgn(paper.left,paper.top,paper.right+1,paper.bottom+1,z,z);
 if(docked&&dockExpanded){RECT flat=side==1?RECT{paper.left,paper.top,paper.left+z,paper.bottom}:RECT{paper.right-z,paper.top,paper.right,paper.bottom};HRGN edge=CreateRectRgnIndirect(&flat);CombineRgn(region,region,edge,RGN_OR);DeleteObject(edge);}
 SetWindowRgn(hwnd,region,TRUE);
}
static void TogglePin(){
 keyboardEditing=false;pinned=!pinned;LONG_PTR style=GetWindowLongPtrW(window,GWL_EXSTYLE);
 SetWindowLongPtrW(window,GWL_EXSTYLE,pinned?style|OverlayStyle():style&~static_cast<LONG_PTR>(OverlayStyle()));
 SetWindowPos(window,pinned?HWND_TOPMOST:HWND_NOTOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE|SWP_FRAMECHANGED);
 SetWindowTextW(pinButton,pinned?L"取消悬浮置顶":L"悬浮置顶，输入框可直接键入");InvalidateRect(pinButton,nullptr,TRUE);NotifyOverlay();
 if(!pinned){SetForegroundWindow(window);if(controller)controller->MoveFocus(COREWEBVIEW2_MOVE_FOCUS_REASON_PROGRAMMATIC);}
}
static void ShowDocked(){
 if(!docked)return;
 if(dockExpanded){
  GetWindowRect(window,&dockOpenBounds);MONITORINFO monitor={sizeof(monitor)};GetMonitorInfoW(MonitorFromWindow(window,MONITOR_DEFAULTTONEAREST),&monitor);
  int x=dockSide==1?monitor.rcWork.left:monitor.rcWork.right-TabSize(),y=dockOpenBounds.top+(dockOpenBounds.bottom-dockOpenBounds.top-TabLength())/2;
  dockClosedBounds={x,y,x+TabSize(),y+TabLength()};
 }
 dockExpanded=!dockExpanded;const RECT&r=dockExpanded?dockOpenBounds:dockClosedBounds;
 SetWindowPos(window,pinned?HWND_TOPMOST:HWND_NOTOPMOST,r.left,r.top,r.right-r.left,r.bottom-r.top,SWP_NOACTIVATE|SWP_SHOWWINDOW);Layout();
}
static int NearestDockSide(const RECT& r,const RECT& work){return abs(r.left-work.left)<=abs(work.right-r.right)?1:2;}
static void ToggleDock(){
 if(docked){
  if(dockExpanded)GetWindowRect(window,&dockOpenBounds);undockedBounds.right=undockedBounds.left+dockOpenBounds.right-dockOpenBounds.left;undockedBounds.bottom=undockedBounds.top+dockOpenBounds.bottom-dockOpenBounds.top;
  docked=false;dockSide=0;dockExpanded=false;
  SetWindowPos(window,nullptr,undockedBounds.left,undockedBounds.top,undockedBounds.right-undockedBounds.left,undockedBounds.bottom-undockedBounds.top,SWP_NOZORDER|SWP_NOACTIVATE);
  if(pinned!=dockWasPinned)TogglePin();Layout();return;
 }
 if(IsZoomed(window))ShowWindow(window,SW_RESTORE);
 GetWindowRect(window,&undockedBounds);dockWasPinned=pinned;if(!pinned)TogglePin();
 MONITORINFO mi={sizeof(mi)};GetMonitorInfoW(MonitorFromWindow(window,MONITOR_DEFAULTTONEAREST),&mi);RECT work=mi.rcWork,r=undockedBounds;
 dockSide=NearestDockSide(r,work);
 int width=min(r.right-r.left,work.right-work.left),height=min(r.bottom-r.top,work.bottom-work.top),t=TabSize(),longer=TabLength();
 int x=max(work.left,min(r.left,work.right-width)),y=max(work.top,min(r.top,work.bottom-height));
 if(dockSide==1)x=work.left;else x=work.right-width;
 dockOpenBounds={x,y,x+width,y+height};
 int tx=dockSide==1?work.left:work.right-t,ty=y+(height-longer)/2;dockClosedBounds={tx,ty,tx+t,ty+longer};
 docked=true;dockExpanded=true;ShowDocked();
}
static LRESULT CALLBACK TabProc(HWND h,UINT m,WPARAM w,LPARAM l,UINT_PTR,DWORD_PTR){
 if(m==WM_NCHITTEST)return HTCLIENT;
 if(m==WM_MOUSEACTIVATE)return MA_NOACTIVATE;
 if(m==WM_LBUTTONDOWN){tabDragging=true;tabPulled=false;GetCursorPos(&tabStart);SetCapture(h);return 0;}
 if(m==WM_MOUSEMOVE&&tabDragging){POINT p;GetCursorPos(&p);if(docked&&!dockExpanded&&(abs(p.x-tabStart.x)+abs(p.y-tabStart.y)>MulDiv(8,GetDpiForWindow(window),96))){tabPulled=true;ShowDocked();}return 0;}
 if(m==WM_LBUTTONUP&&tabDragging){tabDragging=false;ReleaseCapture();if(!tabPulled){if(docked)ShowDocked();else ToggleDock();}return 0;}
 if(m==WM_CAPTURECHANGED)tabDragging=false;
 return DefSubclassProc(h,m,w,l);
}
static RECT ContentBounds(){RECT r=PaperRect();int edge=ResizeBorder();r.left+=edge;r.right-=edge;r.bottom-=edge;r.top+=CaptionHeight();return r;}
static void Layout(){
 if(!window)return;RECT r=PaperRect();bool visible=!docked||dockExpanded;int edge=ResizeBorder(),width=MulDiv(28,GetDpiForWindow(window),96);
 for(int i=0;i<5;i++)if(captionButtons[i]){ShowWindow(captionButtons[i],visible?SW_SHOWNOACTIVATE:SW_HIDE);if(visible)SetWindowPos(captionButtons[i],HWND_TOP,r.right-edge-(5-i)*width,r.top,width,CaptionHeight(),SWP_NOACTIVATE);}
 PositionDockTab();
 RoundWindow(window,docked?dockSide:0);
 if(controller){controller->put_IsVisible(visible);if(visible)controller->put_Bounds(ContentBounds());}InvalidateRect(window,nullptr,TRUE);
}
static void CreateChrome(HINSTANCE instance){
 const wchar_t* names[]={L"贴边收起 / 退出贴边",pinned?L"取消悬浮置顶":L"悬浮置顶，输入框可直接键入",L"最小化",L"最大化 / 还原",L"关闭"};
 for(int i=0;i<5;i++)captionButtons[i]=CreateWindowW(L"BUTTON",names[i],WS_CHILD|WS_VISIBLE|BS_OWNERDRAW,0,0,0,0,window,reinterpret_cast<HMENU>(static_cast<INT_PTR>(4101+i)),instance,nullptr);
 dockTab=CreateWindowExW(WS_EX_LAYERED|WS_EX_NOACTIVATE|WS_EX_TOOLWINDOW,L"STATIC",L"HDR便签：左右贴边收起；点击或拖出展开",WS_POPUP,0,0,0,0,window,nullptr,instance,nullptr);
 SetWindowSubclass(dockTab,TabProc,1,0);
 chromeTips=CreateWindowExW(WS_EX_TOPMOST,TOOLTIPS_CLASSW,nullptr,WS_POPUP|TTS_ALWAYSTIP,0,0,0,0,window,nullptr,instance,nullptr);
 for(HWND button:captionButtons){static wchar_t labels[5][80];int i=int(GetDlgCtrlID(button))-4101;GetWindowTextW(button,labels[i],80);TOOLINFOW ti={sizeof(ti)};ti.uFlags=TTF_IDISHWND|TTF_SUBCLASS;ti.hwnd=window;ti.uId=reinterpret_cast<UINT_PTR>(button);ti.lpszText=labels[i];SendMessageW(chromeTips,TTM_ADDTOOLW,0,reinterpret_cast<LPARAM>(&ti));}
 static wchar_t tabTip[]=L"与工作台相连的便签：点击收起到最近屏幕左/右边缘；再点击或拖出展开";TOOLINFOW ti={sizeof(ti)};ti.uFlags=TTF_IDISHWND|TTF_SUBCLASS;ti.hwnd=window;ti.uId=reinterpret_cast<UINT_PTR>(dockTab);ti.lpszText=tabTip;SendMessageW(chromeTips,TTM_ADDTOOLW,0,reinterpret_cast<LPARAM>(&ti));
 pinButton=captionButtons[1];SetWindowPos(window,nullptr,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOZORDER|SWP_FRAMECHANGED);Layout();
}
static bool ValidModule(const std::wstring& name){return name==L"auto"||name==L"budget"||name==L"halo"||name==L"pattern"||name==L"sensors"||name==L"save";}
static std::wstring ModuleTitle(const std::wstring& name){if(name==L"auto")return L"全自动联合调整";if(name==L"budget")return L"APL与ABL控制";if(name==L"halo")return L"光晕与控光";if(name==L"pattern")return L"HDR图样控制";if(name==L"sensors")return L"传感器与记录";return L"配置与设备";}
static void DetachModule(const std::wstring& name){
 if(!ValidModule(name)||!backend)return;
 std::wstring cls=L"MIHDRControlWindow-v093-"+serverPort+L"-"+name;HWND existing=FindWindowW(cls.c_str(),nullptr);
 if(existing){PostMessageW(existing,WM_APP+2,0,0);return;}
 std::wstring command=L"\""+exePath+L"\" --module "+name+L" --port "+serverPort+L" --backend "+std::to_wstring(sharedBackend);
 STARTUPINFOW info={sizeof(info)};PROCESS_INFORMATION process={};
 if(CreateProcessW(exePath.c_str(),command.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,root.c_str(),&info,&process)){CloseHandle(process.hThread);CloseHandle(process.hProcess);}
}
static ULONGLONG started;
static HANDLE Python(const std::wstring& args){
 std::wstring python=root+L"\\tools\\python\\pythonw.exe",cmd=L"\""+python+L"\" "+args;
 STARTUPINFOW s={sizeof(s)};PROCESS_INFORMATION p={};
 if(!CreateProcessW(python.c_str(),cmd.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,root.c_str(),&s,&p))return nullptr;
 CloseHandle(p.hThread);return p.hProcess;
}
static void Theme(bool dark){
 darkTheme=dark;
 BOOL enabled=dark;DwmSetWindowAttribute(window,20,&enabled,sizeof(enabled));
 ComPtr<ICoreWebView2Controller2> colors;
 if(controller&&SUCCEEDED(controller.As(&colors))){BYTE c=dark?12:246;colors->put_DefaultBackgroundColor({255,c,c,c});}
 PositionDockTab();RedrawWindow(window,nullptr,nullptr,RDW_INVALIDATE|RDW_ALLCHILDREN);
}
static void CloseFallback(){if(!stopProcess)stopProcess=Python(L"\""+root+L"\\lab\\stop.py\"");}
static void SaveConfigAs(const std::wstring& payload){
 size_t split=payload.find(L'\n');if(split==std::wstring::npos)return;
 std::wstring name=payload.substr(0,split),content=payload.substr(split+1),initial=root+L"\\profiles";
 wchar_t path[32768]={};wcsncpy_s(path,name.c_str(),_TRUNCATE);
 OPENFILENAMEW choice={sizeof(choice)};choice.hwndOwner=window;choice.lpstrFile=path;choice.nMaxFile=32768;
 choice.lpstrTitle=L"导出控制器配置";choice.lpstrFilter=L"JSON 配置 (*.json)\0*.json\0\0";choice.lpstrDefExt=L"json";choice.lpstrInitialDir=initial.c_str();
 choice.Flags=OFN_OVERWRITEPROMPT|OFN_PATHMUSTEXIST|OFN_NOCHANGEDIR;
 const wchar_t* status=L"canceled";KeyboardEditing(true);
 if(GetSaveFileNameW(&choice)){
  int size=WideCharToMultiByte(CP_UTF8,0,content.c_str(),static_cast<int>(content.size()),nullptr,0,nullptr,nullptr);
  std::string bytes(size,'\0');WideCharToMultiByte(CP_UTF8,0,content.c_str(),static_cast<int>(content.size()),bytes.data(),size,nullptr,nullptr);
  std::ofstream file(std::filesystem::path(path),std::ios::binary);file.write(bytes.data(),bytes.size());file.flush();status=file?L"saved":L"error";
 }else if(CommDlgExtendedError())status=L"error";
 KeyboardEditing(false);
 if(view)view->ExecuteScript((L"window.miConfigExported&&window.miConfigExported('"+std::wstring(status)+L"')").c_str(),nullptr);
}
static void Fail(const wchar_t* text){MessageBoxW(window,text,L"MI HDR Control",MB_OK|MB_ICONERROR);closing=true;DestroyWindow(window);}
static void WebView(){
 environmentStarted=true;
 auto made=Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>([](HRESULT result,ICoreWebView2Environment* environment)->HRESULT{
  if(FAILED(result)||!environment){Fail(L"无法创建 WebView2。请确认系统已安装 Microsoft Edge WebView2 Runtime。服务会自动结束。");return S_OK;}
  return environment->CreateCoreWebView2Controller(window,Callback<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>([](HRESULT result,ICoreWebView2Controller* created)->HRESULT{
   if(FAILED(result)||!created){Fail(L"无法打开控制窗口。服务会自动结束，详情见 logs/service.log。");return S_OK;}
   controller=created;controller->get_CoreWebView2(&view);Layout();Theme(true);
   view->AddScriptToExecuteOnDocumentCreated(L"window.miNativeHost=true;",nullptr);
   ComPtr<ICoreWebView2_4> downloads;if(SUCCEEDED(view.As(&downloads))){EventRegistrationToken token;downloads->add_DownloadStarting(Callback<ICoreWebView2DownloadStartingEventHandler>([](ICoreWebView2*,ICoreWebView2DownloadStartingEventArgs* args)->HRESULT{args->put_Cancel(TRUE);return S_OK;}).Get(),&token);}
   ComPtr<ICoreWebView2Settings> settings;view->get_Settings(&settings);settings->put_IsStatusBarEnabled(FALSE);settings->put_IsZoomControlEnabled(FALSE);
   EventRegistrationToken token;
   view->add_NavigationCompleted(Callback<ICoreWebView2NavigationCompletedEventHandler>([](ICoreWebView2*,ICoreWebView2NavigationCompletedEventArgs*)->HRESULT{NotifyOverlay();return S_OK;}).Get(),&token);
   view->add_WebMessageReceived(Callback<ICoreWebView2WebMessageReceivedEventHandler>([](ICoreWebView2*,ICoreWebView2WebMessageReceivedEventArgs* args)->HRESULT{
    LPWSTR raw=nullptr;if(SUCCEEDED(args->TryGetWebMessageAsString(&raw))){std::wstring m(raw);CoTaskMemFree(raw);
      if(m==L"request-close")PostMessageW(window,WM_CLOSE,0,0);else if(m==L"keyboard-focus")KeyboardEditing(true);else if(m==L"exit-fallback")CloseFallback();else if(m==L"theme:dark")Theme(true);else if(m==L"theme:light")Theme(false);else if(m.rfind(L"save-config:",0)==0)SaveConfigAs(m.substr(12));else if(m.rfind(L"detach:",0)==0)DetachModule(m.substr(7));else if(m==L"close-module-ready"&&moduleWindow)DestroyWindow(window);
    }return S_OK;
   }).Get(),&token);
   view->add_NewWindowRequested(Callback<ICoreWebView2NewWindowRequestedEventHandler>([](ICoreWebView2*,ICoreWebView2NewWindowRequestedEventArgs* args)->HRESULT{
    args->put_Handled(TRUE);return S_OK;
   }).Get(),&token);
   view->Navigate(url.c_str());return S_OK;
  }).Get());
 });
 std::wstring data=root+L"\\state\\webview";
 if(FAILED(CreateCoreWebView2EnvironmentWithOptions(nullptr,data.c_str(),nullptr,made.Get())))Fail(L"未能启动 WebView2。请安装微软 WebView2 Runtime。本程序不会静默安装或请求管理员权限。");
}
static LRESULT CALLBACK WindowProc(HWND hwnd,UINT m,WPARAM w,LPARAM l){
 switch(m){
 case WM_APP+2:if(docked){if(IsIconic(hwnd))ShowWindow(hwnd,SW_RESTORE);if(!dockExpanded)ShowDocked();Layout();return 0;}if(moduleWindow&&!pinned)TogglePin();ShowWindow(hwnd,pinned?SW_SHOWNOACTIVATE:SW_RESTORE);SetWindowPos(hwnd,pinned?HWND_TOPMOST:HWND_TOP,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);return 0;
 case WM_MOUSEACTIVATE:if(pinned&&!keyboardEditing)return MA_NOACTIVATE;break;
 case WM_APP+1:Layout();return 0;
 case WM_SHOWWINDOW:if(w){if(controller)controller->put_IsVisible(TRUE);PostMessageW(hwnd,WM_APP+1,0,0);}break;
 case WM_ACTIVATE:if(LOWORD(w)==WA_INACTIVE)KeyboardEditing(false);Layout();break;
 case WM_SETFOCUS:if(controller)controller->MoveFocus(COREWEBVIEW2_MOVE_FOCUS_REASON_PROGRAMMATIC);return 0;
 case WM_NCCALCSIZE:return 0;
 case WM_NCPAINT:return 0;
 case WM_NCACTIVATE:return TRUE;
 case WM_ERASEBKGND:{RECT r;GetClientRect(hwnd,&r);HBRUSH brush=CreateSolidBrush(ChromeBackground());FillRect(reinterpret_cast<HDC>(w),&r,brush);DeleteObject(brush);return 1;}
 case WM_MOVE:PositionDockTab();break;
 case WM_SIZE:if(w!=SIZE_MINIMIZED)Layout();else if(dockTab)ShowWindow(dockTab,SW_HIDE);return 0;
 case WM_DPICHANGED:{RECT* r=reinterpret_cast<RECT*>(l);SetWindowPos(hwnd,nullptr,r->left,r->top,r->right-r->left,r->bottom-r->top,SWP_NOZORDER|SWP_NOACTIVATE);Layout();return 0;}
 case WM_GETMINMAXINFO:{auto info=reinterpret_cast<MINMAXINFO*>(l);MONITORINFO monitor={sizeof(monitor)};GetMonitorInfoW(MonitorFromWindow(hwnd,MONITOR_DEFAULTTONEAREST),&monitor);info->ptMaxPosition={monitor.rcWork.left-monitor.rcMonitor.left,monitor.rcWork.top-monitor.rcMonitor.top};info->ptMaxSize={monitor.rcWork.right-monitor.rcWork.left,monitor.rcWork.bottom-monitor.rcWork.top};if(docked&&!dockExpanded){int t=TabSize(),n=TabLength();info->ptMinTrackSize=POINT{t,n};}else info->ptMinTrackSize={MulDiv(320,GetDpiForWindow(hwnd),96),MulDiv(240,GetDpiForWindow(hwnd),96)};return 0;}
 case WM_NCHITTEST:{POINT p={GET_X_LPARAM(l),GET_Y_LPARAM(l)};ScreenToClient(hwnd,&p);RECT r=PaperRect();int edge=ResizeBorder();if(docked&&!dockExpanded)return HTCLIENT;
  if(!IsZoomed(hwnd)){bool left=p.x<r.left+edge,right=p.x>=r.right-edge,top=p.y<r.top+edge,bottom=p.y>=r.bottom-edge;if(top)return left?HTTOPLEFT:right?HTTOPRIGHT:HTTOP;if(bottom)return left?HTBOTTOMLEFT:right?HTBOTTOMRIGHT:HTBOTTOM;if(left)return HTLEFT;if(right)return HTRIGHT;}
  for(HWND button:captionButtons)if(button){RECT area;GetWindowRect(button,&area);POINT screen=p;ClientToScreen(hwnd,&screen);if(PtInRect(&area,screen))return HTCLIENT;}
  return p.x>=r.left&&p.x<r.right&&p.y>=r.top&&p.y<r.top+CaptionHeight()?HTCAPTION:HTCLIENT;}
 case WM_EXITSIZEMOVE:{if(!docked&&!IsZoomed(hwnd)){RECT r;GetWindowRect(hwnd,&r);MONITORINFO mi={sizeof(mi)};GetMonitorInfoW(MonitorFromWindow(hwnd,MONITOR_DEFAULTTONEAREST),&mi);int snap=MulDiv(20,GetDpiForWindow(hwnd),96);if(min(abs(r.left-mi.rcWork.left),abs(mi.rcWork.right-r.right))<=snap)ToggleDock();}return 0;}
 case WM_COMMAND:if(HIWORD(w)==BN_CLICKED){switch(LOWORD(w)){case 4101:ToggleDock();return 0;case 4102:TogglePin();return 0;case 4103:ShowWindow(hwnd,SW_MINIMIZE);return 0;case 4104:ShowWindow(hwnd,IsZoomed(hwnd)?SW_RESTORE:SW_MAXIMIZE);return 0;case 4105:PostMessageW(hwnd,WM_CLOSE,0,0);return 0;}}break;
 case WM_DRAWITEM:{auto d=reinterpret_cast<DRAWITEMSTRUCT*>(l);int index=int(d->CtlID)-4101;if(index<0||index>4)break;
  COLORREF bg=ChromeBackground(),fg=darkTheme?RGB(220,220,220):RGB(40,40,40);
  if(d->itemState&ODS_SELECTED)bg=darkTheme?RGB(55,55,55):RGB(215,215,215);
  HBRUSH brush=CreateSolidBrush(bg);FillRect(d->hDC,&d->rcItem,brush);DeleteObject(brush);
  HPEN pen=CreatePen(PS_SOLID,max(1,MulDiv(1,GetDpiForWindow(hwnd),96)),index==1&&pinned?RGB(110,185,110):fg);auto old=SelectObject(d->hDC,pen);
  int x=(d->rcItem.left+d->rcItem.right)/2,y=(d->rcItem.top+d->rcItem.bottom)/2,z=MulDiv(4,GetDpiForWindow(hwnd),96);
  auto line=[&](int a,int b,int c,int e){MoveToEx(d->hDC,a,b,nullptr);LineTo(d->hDC,c,e);};
  if(index==0){line(x-z-1,y-z,x-z-1,y+z);line(x+z,y-z,x+z,y+z);line(x-z-1,y-z,x+z,y-z);line(x-z-1,y+z,x+z,y+z);line(x-1,y-z,x-1,y+z);}
  if(index==1){line(x-z,y-z,x+z,y-z);line(x-z/2,y-z,x-z/2,y);line(x+z/2,y-z,x+z/2,y);line(x-z,y+1,x+z,y+1);line(x,y+1,x,y+z+3);if(pinned)line(x-z-2,y+z+2,x+z+2,y-z-2);}
  if(index==2)line(x-z,y+2,x+z,y+2);
  if(index==3){auto fill=SelectObject(d->hDC,GetStockObject(NULL_BRUSH));Rectangle(d->hDC,x-z,y-z,x+z,y+z);SelectObject(d->hDC,fill);}
  if(index==4){line(x-z,y-z,x+z,y+z);line(x-z,y+z,x+z,y-z);}
  SelectObject(d->hDC,old);DeleteObject(pen);return TRUE;}
 case WM_PAINT:{PAINTSTRUCT p;HDC dc=BeginPaint(hwnd,&p);RECT r=PaperRect();RECT title=r;title.bottom=title.top+CaptionHeight();HBRUSH brush=CreateSolidBrush(ChromeBackground());FillRect(dc,&title,brush);DeleteObject(brush);SetBkMode(dc,TRANSPARENT);SetTextColor(dc,darkTheme?RGB(220,220,220):RGB(35,35,35));HFONT font=CreateFontW(-MulDiv(11,GetDpiForWindow(hwnd),96),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Segoe UI");auto old=SelectObject(dc,font);title.left+=12;title.right-=MulDiv(152,GetDpiForWindow(hwnd),96);wchar_t text[256];GetWindowTextW(hwnd,text,256);DrawTextW(dc,text,-1,&title,DT_LEFT|DT_VCENTER|DT_SINGLELINE|DT_END_ELLIPSIS);SelectObject(dc,old);DeleteObject(font);if(!view){r.top+=CaptionHeight();DrawTextW(dc,L"正在启动控制器…",-1,&r,DT_CENTER|DT_VCENTER|DT_SINGLELINE);}EndPaint(hwnd,&p);return 0;}
 case WM_SETTEXT:{LRESULT result=DefWindowProcW(hwnd,m,w,l);InvalidateRect(hwnd,nullptr,TRUE);return result;}
 case WM_TIMER:
  if(backend&&WaitForSingleObject(backend,0)==WAIT_OBJECT_0){DestroyWindow(hwnd);return 0;}
  if(!environmentStarted){std::wifstream input{std::filesystem::path(readyFile)};DWORD pid=0;
   if(input&&std::getline(input,url)&&(input>>pid)&&pid){sharedBackend=pid;backend=OpenProcess(SYNCHRONIZE,FALSE,pid);if(!backend){Fail(L"服务已退出，请查看 logs/service.log。");return 0;}WebView();}
   else if((preparation&&WaitForSingleObject(preparation,0)==WAIT_OBJECT_0)||GetTickCount64()-started>30000)Fail(L"控制器未启动。可能有其他目录的副本占用端口，请先退出旧版；详情见 logs/service.log。");
  }return 0;
 case WM_CLOSE:
  if(closing)return 0;closing=true;
  if(moduleWindow){if(view)view->ExecuteScript(L"window.miCloseModule ? window.miCloseModule() : window.chrome.webview.postMessage(\"close-module-ready\")",nullptr);else DestroyWindow(hwnd);return 0;}SetWindowTextW(hwnd,L"MI HDR Control · 正在保存配置并结束控制器…");
  if(view)view->ExecuteScript(L"window.miExit ? window.miExit() : window.chrome.webview.postMessage('exit-fallback')",nullptr);else{if(backend)CloseFallback();DestroyWindow(hwnd);}return 0;
 case WM_DESTROY:if(dockTab){DestroyWindow(dockTab);dockTab=nullptr;}if(controller)controller->Close();view.Reset();controller.Reset();PostQuitMessage(0);return 0;
 }return DefWindowProcW(hwnd,m,w,l);
}
static bool StartupDockedExpanded(){return !moduleWindow;}
static RECT DefaultMainBounds(const RECT& work,int dpi){
 int height=min(MulDiv(960,dpi,96),work.bottom-work.top),width=height*210/297+MulDiv(30,dpi,96);
 width=min(width,work.right-work.left);int y=work.top+(work.bottom-work.top-height)/2;return RECT{work.left,y,work.left+width,y+height};
}
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE,PWSTR,int){
 wchar_t path[32768];DWORD n=GetModuleFileNameW(nullptr,path,32768);if(!n||n>=32768)return 1;exePath.assign(path,n);root.assign(path,n);root.resize(root.find_last_of(L"\\/"));PortableEnvironment();
 wchar_t port[16]=L"18533";if(!GetEnvironmentVariableW(L"MI_CONTROL_PORT",port,16))wcscpy_s(port,L"18533");
 int argc=0;LPWSTR* args=CommandLineToArgvW(GetCommandLineW(),&argc);serverPort=port;
 for(int i=1;i+1<argc;i++){std::wstring option=args[i];if(option==L"--module"){moduleName=args[++i];moduleWindow=ValidModule(moduleName);}else if(option==L"--port")serverPort=args[++i];else if(option==L"--backend")sharedBackend=wcstoul(args[++i],nullptr,10);}LocalFree(args);SetEnvironmentVariableW(L"MI_CONTROL_PORT",serverPort.c_str());
 std::wstring name=L"MIHDRControlWindow-v093-"+serverPort+(moduleWindow?L"-"+moduleName:L"");HANDLE mutex=CreateMutexW(nullptr,TRUE,(L"Local\\"+name).c_str());
 if(GetLastError()==ERROR_ALREADY_EXISTS){HWND other=FindWindowW(name.c_str(),nullptr);if(other)PostMessageW(other,WM_APP+2,0,0);CloseHandle(mutex);return 0;}
 SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);if(FAILED(CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED)))return 1;
 Gdiplus::GdiplusStartupInput gdiInput;if(Gdiplus::GdiplusStartup(&tabGdiToken,&gdiInput,nullptr)!=Gdiplus::Ok)return 1;
 WNDCLASSW wc={};wc.lpfnWndProc=WindowProc;wc.hInstance=instance;wc.lpszClassName=name.c_str();wc.hbrBackground=CreateSolidBrush(RGB(12,12,12));wc.hCursor=LoadCursor(nullptr,IDC_ARROW);wc.hIcon=static_cast<HICON>(LoadImageW(instance,L"IDI_APP",IMAGE_ICON,0,0,LR_DEFAULTSIZE));RegisterClassW(&wc);
 RECT work;SystemParametersInfoW(SPI_GETWORKAREA,0,&work,0);RECT bounds=DefaultMainBounds(work,GetDpiForSystem());
 if(moduleWindow){int width=min(900,work.right-work.left),height=min(750,work.bottom-work.top);bounds={work.left+(work.right-work.left-width)/2,work.top+(work.bottom-work.top-height)/2,work.left+(work.right-work.left+width)/2,work.top+(work.bottom-work.top+height)/2};}
 pinned=true;docked=StartupDockedExpanded();dockExpanded=docked;dockSide=docked?1:0;dockWasPinned=false;undockedBounds=bounds;dockOpenBounds=bounds;
 window=CreateWindowExW(OverlayStyle(),name.c_str(),(moduleWindow?(L"MI HDR Control 0.9.26-public-preview · "+ModuleTitle(moduleName)).c_str():L"MI HDR Control 0.9.26-public-preview · 显示调节工作台"),WS_POPUP|WS_THICKFRAME|WS_MINIMIZEBOX|WS_MAXIMIZEBOX|WS_SYSMENU|WS_CLIPCHILDREN,bounds.left,bounds.top,bounds.right-bounds.left,bounds.bottom-bounds.top,nullptr,nullptr,instance,nullptr);
 if(docked)GetWindowRect(window,&dockOpenBounds);
 CreateChrome(instance);
 Theme(true);ShowWindow(window,pinned?SW_SHOWNOACTIVATE:SW_SHOW);UpdateWindow(window);std::filesystem::create_directories(root+L"\\tmp");readyFile=root+L"\\tmp\\desktop-"+std::to_wstring(GetCurrentProcessId())+L".txt";
 if(moduleWindow){backend=OpenProcess(SYNCHRONIZE,FALSE,sharedBackend);if(!backend){DestroyWindow(window);return 2;}url=L"http://127.0.0.1:"+serverPort+L"/?module="+moduleName;WebView();}
 else preparation=Python(L"\""+root+L"\\lab\\launch.py\" --desktop-ready \""+readyFile+L"\" --owner "+std::to_wstring(GetCurrentProcessId()));
 started=GetTickCount64();SetTimer(window,1,100,nullptr);
 MSG msg;while(GetMessageW(&msg,nullptr,0,0)>0){TranslateMessage(&msg);DispatchMessageW(&msg);}
 DeleteFileW(readyFile.c_str());if(preparation)CloseHandle(preparation);if(backend)CloseHandle(backend);if(stopProcess)CloseHandle(stopProcess);DeleteObject(wc.hbrBackground);Gdiplus::GdiplusShutdown(tabGdiToken);CoUninitialize();ReleaseMutex(mutex);CloseHandle(mutex);return 0;
}
