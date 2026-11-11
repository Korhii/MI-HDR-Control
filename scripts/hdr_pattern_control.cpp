#define NOMINMAX
#include <windows.h>
#include <windowsx.h>
#include <commctrl.h>
#pragma comment(lib,"comctl32.lib")
#include <d3d11_1.h>
#include <dxgi1_6.h>
#include <dwmapi.h>
#pragma comment(lib,"dwmapi.lib")
#include <wrl/client.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
using Microsoft::WRL::ComPtr;
namespace fs=std::filesystem;
static void check(HRESULT h,const char* op){if(FAILED(h))throw std::runtime_error(std::string(op)+": "+std::to_string(h));}
static double pq(double n){double p=std::pow(n/10000.,2610./16384.);return std::pow((3424./4096.+2413./128.*p)/(1+2392./128.*p),2523./32.);}
static uint32_t packed(double n){uint32_t c=uint32_t(std::lround(pq(n)*1023));return 0xc0000000U|c|(c<<10)|(c<<20);}
static std::wstring wide(const std::string& s){int n=MultiByteToWideChar(CP_UTF8,0,s.data(),int(s.size()),nullptr,0);std::wstring w(n,0);MultiByteToWideChar(CP_UTF8,0,s.data(),int(s.size()),w.data(),n);return w;}
static std::string escaped(const std::string& s){std::string r;for(char c:s){if(c=='"'||c=='\\')r+='\\';if(c=='\n')r+="\\n";else if(c=='\r'){}else r+=c;}return r;}
static bool previewWindowed=false,patternPinned=false,patternHidden=true,patternViewChanged=false,patternSizing=false;
static bool previewPinned=false,patternTicking=false,patternMenuOpen=false,patternHotkeyRegistered=false;
static void patternHotkey(HWND w,bool enabled){
    if(patternHotkeyRegistered){UnregisterHotKey(w,5206);patternHotkeyRegistered=false;}
    if(enabled&&!patternHidden&&!previewWindowed)patternHotkeyRegistered=RegisterHotKey(w,5206,MOD_NOREPEAT,VK_OEM_3)!=0;
}static std::string patternFailure;
static WINDOWPLACEMENT previewPlacement={sizeof(WINDOWPLACEMENT)};
static RECT previewRestore={},patternMonitor={};static HWND patternButtons[5]={},patternSurface=nullptr;
static std::function<void()> patternTick;
static HANDLE patternFrameReady=nullptr;static bool patternFrameAllowed=false;
static int patternUnit(HWND w,int value){return MulDiv(value,GetDpiForWindow(w),96);}
static RECT patternContent(HWND w){RECT r;GetClientRect(w,&r);int edge=previewWindowed&&!IsZoomed(w)?patternUnit(w,6):0;r.left+=edge;r.right-=edge;r.top+=previewWindowed?patternUnit(w,22):0;r.bottom-=edge;return r;}
static void positionPatternButtons(HWND w){
    RECT r;GetClientRect(w,&r);int width=patternUnit(w,30),edge=previewWindowed&&!IsZoomed(w)?patternUnit(w,6):0;
    static int shapeWidth=-1,shapeHeight=-1;static bool shapeRounded=false;bool rounded=previewWindowed&&!IsZoomed(w);
    if(shapeWidth!=r.right||shapeHeight!=r.bottom||shapeRounded!=rounded){shapeWidth=r.right;shapeHeight=r.bottom;shapeRounded=rounded;if(rounded)SetWindowRgn(w,CreateRoundRectRgn(0,0,r.right+1,r.bottom+1,patternUnit(w,16),patternUnit(w,16)),TRUE);else SetWindowRgn(w,nullptr,TRUE);}
    RECT view=patternContent(w);if(patternSurface)MoveWindow(patternSurface,view.left,view.top,std::max(1L,view.right-view.left),std::max(1L,view.bottom-view.top),TRUE);
    for(int i=0;i<5;i++)if(patternButtons[i])SetWindowPos(patternButtons[i],HWND_TOP,r.right-(5-i)*width-edge,0,width,patternUnit(w,22),SWP_NOACTIVATE);
}
static void togglePatternFullscreen(HWND w){
    LONG_PTR visible=GetWindowLongPtrW(w,GWL_STYLE)&WS_VISIBLE;
    if(previewWindowed){
        GetWindowPlacement(w,&previewPlacement);previewPinned=patternPinned;GetWindowRect(w,&previewRestore);
        MONITORINFO mi={sizeof(mi)};GetMonitorInfoW(MonitorFromWindow(w,MONITOR_DEFAULTTONEAREST),&mi);patternMonitor=mi.rcMonitor;
        previewWindowed=false;SetWindowLongPtrW(w,GWL_STYLE,WS_POPUP|WS_CLIPCHILDREN|visible);
        SetWindowPos(w,patternPinned?HWND_TOPMOST:HWND_NOTOPMOST,patternMonitor.left,patternMonitor.top,patternMonitor.right-patternMonitor.left,patternMonitor.bottom-patternMonitor.top,SWP_FRAMECHANGED|SWP_NOACTIVATE);
    }else{
        previewWindowed=true;patternPinned=previewPinned;SetWindowLongPtrW(w,GWL_STYLE,WS_POPUP|WS_THICKFRAME|WS_MINIMIZEBOX|WS_MAXIMIZEBOX|WS_SYSMENU|WS_CLIPCHILDREN|visible);
        SetWindowPos(w,patternPinned?HWND_TOPMOST:HWND_NOTOPMOST,previewRestore.left,previewRestore.top,previewRestore.right-previewRestore.left,previewRestore.bottom-previewRestore.top,SWP_FRAMECHANGED|SWP_NOACTIVATE);
        SetWindowPlacement(w,&previewPlacement);
    }
    patternHotkey(w,GetAncestor(GetForegroundWindow(),GA_ROOT)==w);patternMenuOpen=false;patternViewChanged=true;positionPatternButtons(w);InvalidateRect(w,nullptr,TRUE);
}
static bool patternMenuKey(UINT message,WPARAM key){return (message==WM_KEYDOWN&&key==VK_OEM_3)||(message==WM_CHAR&&(key==L'·'||key==L'`'));}
static bool patternAnnotationVisible(bool detailedLabel){return !patternHidden||detailedLabel;}
static void showPatternControls(bool){for(HWND b:patternButtons)if(b){bool show=!patternHidden&&(previewWindowed||patternMenuOpen);if(bool(GetWindowLongPtrW(b,GWL_STYLE)&WS_VISIBLE)!=show)ShowWindow(b,show?SW_SHOWNOACTIVATE:SW_HIDE);}}
static void createPatternButtons(HWND w){
    const wchar_t* text[]={L"置顶",L"最小化",L"最大化 / 还原",L"全屏 / 返回窗口",L"关闭图样"};
    for(int i=0;i<5;i++)patternButtons[i]=CreateWindowW(L"BUTTON",text[i],WS_CHILD|BS_OWNERDRAW,0,0,0,0,w,reinterpret_cast<HMENU>(static_cast<INT_PTR>(5201+i)),GetModuleHandleW(nullptr),nullptr);
    positionPatternButtons(w);showPatternControls(false);
}
static LRESULT CALLBACK wndproc(HWND w,UINT m,WPARAM k,LPARAM l){
    if(m==WM_ACTIVATE){patternHotkey(w,LOWORD(k)!=WA_INACTIVE);}
    if(m==WM_HOTKEY&&k==5206&&!previewWindowed){patternMenuOpen=!patternMenuOpen;patternViewChanged=true;showPatternControls(false);return 0;}
    if(m==WM_SETCURSOR){SetCursor(LoadCursor(nullptr,IDC_ARROW));return TRUE;}
    if(!previewWindowed&&!patternHotkeyRegistered&&patternMenuKey(m,k)){if(!(l&(1LL<<30))){patternMenuOpen=!patternMenuOpen;patternViewChanged=true;showPatternControls(false);}return 0;}
    if(m==WM_NCCALCSIZE&&k)return 0;
    if(m==WM_GETMINMAXINFO){auto size=reinterpret_cast<MINMAXINFO*>(l);size->ptMinTrackSize={patternUnit(w,480),patternUnit(w,300)};if(previewWindowed){MONITORINFO mi={sizeof(mi)};GetMonitorInfoW(MonitorFromWindow(w,MONITOR_DEFAULTTONEAREST),&mi);size->ptMaxPosition={mi.rcWork.left-mi.rcMonitor.left,mi.rcWork.top-mi.rcMonitor.top};size->ptMaxSize={mi.rcWork.right-mi.rcWork.left,mi.rcWork.bottom-mi.rcWork.top};}return 0;}
    if(m==WM_SIZE){if(k!=SIZE_MINIMIZED){positionPatternButtons(w);patternViewChanged=true;InvalidateRect(w,nullptr,FALSE);}return 0;}
    if(m==WM_ENTERSIZEMOVE){patternSizing=true;return 0;}if(m==WM_EXITSIZEMOVE){patternSizing=false;patternViewChanged=true;return 0;}
    if(m==WM_DPICHANGED){auto r=reinterpret_cast<RECT*>(l);SetWindowPos(w,nullptr,r->left,r->top,r->right-r->left,r->bottom-r->top,SWP_NOZORDER|SWP_NOACTIVATE);positionPatternButtons(w);patternViewChanged=true;return 0;}
    if(m==WM_NCHITTEST&&previewWindowed){POINT p={GET_X_LPARAM(l),GET_Y_LPARAM(l)};ScreenToClient(w,&p);RECT r;GetClientRect(w,&r);int e=IsZoomed(w)?0:patternUnit(w,6);bool left=p.x<e,right=p.x>=r.right-e,top=p.y<e,bottom=p.y>=r.bottom-e;if(top)return left?HTTOPLEFT:right?HTTOPRIGHT:HTTOP;if(bottom)return left?HTBOTTOMLEFT:right?HTBOTTOMRIGHT:HTBOTTOM;if(left)return HTLEFT;if(right)return HTRIGHT;for(HWND b:patternButtons){RECT a;GetWindowRect(b,&a);POINT q=p;ClientToScreen(w,&q);if(IsWindowVisible(b)&&PtInRect(&a,q))return HTCLIENT;}if(p.y<patternUnit(w,22))return HTCAPTION;return HTCLIENT;}
    if(m==WM_TIMER&&k==5200){
        showPatternControls(false);
        if(!patternFrameAllowed&&patternFrameReady&&WaitForSingleObject(patternFrameReady,0)==WAIT_OBJECT_0)patternFrameAllowed=true;
        if(patternTick&&!patternTicking){patternTicking=true;try{patternTick();}catch(const std::exception& e){patternFailure=e.what();DestroyWindow(w);}patternTicking=false;}patternFrameAllowed=false;return 0;
    }
    if(m==WM_COMMAND&&HIWORD(k)==BN_CLICKED){switch(LOWORD(k)){case 5201:patternPinned=!patternPinned;SetWindowPos(w,patternPinned?HWND_TOPMOST:HWND_NOTOPMOST,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);InvalidateRect(patternButtons[0],nullptr,TRUE);return 0;case 5202:ShowWindow(w,SW_MINIMIZE);return 0;case 5203:if(!previewWindowed)togglePatternFullscreen(w);ShowWindow(w,IsZoomed(w)?SW_RESTORE:SW_MAXIMIZE);return 0;case 5204:togglePatternFullscreen(w);return 0;case 5205:DestroyWindow(w);return 0;}}
    if(m==WM_PAINT){PAINTSTRUCT p;HDC dc=BeginPaint(w,&p);if(previewWindowed){RECT r;GetClientRect(w,&r);r.bottom=patternUnit(w,22);HBRUSH bg=CreateSolidBrush(RGB(20,20,20));FillRect(dc,&r,bg);DeleteObject(bg);SetBkMode(dc,TRANSPARENT);SetTextColor(dc,RGB(230,230,230));HFONT font=CreateFontW(-patternUnit(w,12),0,0,0,FW_NORMAL,0,0,0,DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,DEFAULT_PITCH,L"Segoe UI");auto old=SelectObject(dc,font);r.left=patternUnit(w,12);r.right-=patternUnit(w,190);DrawTextW(dc,L"MI HDR 图样 · 窗口预览",-1,&r,DT_SINGLELINE|DT_VCENTER|DT_END_ELLIPSIS);SelectObject(dc,old);DeleteObject(font);}EndPaint(w,&p);return 0;}
    if(m==WM_DRAWITEM){auto d=reinterpret_cast<DRAWITEMSTRUCT*>(l);int i=int(d->CtlID)-5201;if(i<0||i>4)return FALSE;HBRUSH bg=CreateSolidBrush(RGB(20,20,20));FillRect(d->hDC,&d->rcItem,bg);DeleteObject(bg);HPEN pen=CreatePen(PS_SOLID,1,i==0&&patternPinned?RGB(120,210,150):RGB(230,230,230));auto old=SelectObject(d->hDC,pen);int x=(d->rcItem.right+d->rcItem.left)/2,y=(d->rcItem.top+d->rcItem.bottom)/2,z=patternUnit(w,4);auto line=[&](int a,int b,int c,int e){MoveToEx(d->hDC,a,b,nullptr);LineTo(d->hDC,c,e);};if(i==0){line(x-z+1,y-z,x+z-1,y-z);line(x-z+2,y-z,x-z+2,y);line(x+z-2,y-z,x+z-2,y);line(x-z,y+1,x+z,y+1);line(x,y+1,x,y+z+2);}if(i==1)line(x-z,y+2,x+z,y+2);if(i==2){auto fill=SelectObject(d->hDC,GetStockObject(NULL_BRUSH));Rectangle(d->hDC,x-z,y-z,x+z,y+z);SelectObject(d->hDC,fill);}if(i==3){line(x-z,y-1,x-z,y-z);line(x-z,y-z,x-1,y-z);line(x+1,y-z,x+z,y-z);line(x+z,y-z,x+z,y-1);line(x-z,y+1,x-z,y+z);line(x-z,y+z,x-1,y+z);line(x+1,y+z,x+z,y+z);line(x+z,y+z,x+z,y+1);}if(i==4){line(x-z,y-z,x+z,y+z);line(x-z,y+z,x+z,y-z);}SelectObject(d->hDC,old);DeleteObject(pen);return TRUE;}
    if((m==WM_KEYDOWN&&k==VK_ESCAPE)||m==WM_CLOSE){DestroyWindow(w);return 0;}if(m==WM_DESTROY){patternHotkey(w,false);KillTimer(w,5200);PostQuitMessage(0);return 0;}return DefWindowProcW(w,m,k,l);
}
static std::vector<HMONITOR> monitors;
static BOOL CALLBACK enumMonitor(HMONITOR h,HDC,LPRECT,LPARAM){monitors.push_back(h);return TRUE;}
struct Config {
    int sequence=0,pixelWidth=0,pixelHeight=0,rows=1,cols=1,label=0;
    double area=50,nits=4000,background=0;
};
static std::string sharedText(const fs::path& path,bool required=true){
    HANDLE file=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE){if(required)throw std::runtime_error("Cannot read pattern config");return "";}
    char buffer[4096];DWORD count=0;BOOL ok=ReadFile(file,buffer,sizeof(buffer),&count,nullptr);CloseHandle(file);
    if(!ok)throw std::runtime_error("Cannot read pattern file");return std::string(buffer,count);
}
static Config readConfig(const fs::path& path){
    std::istringstream f(sharedText(path));
    std::map<std::string,double> v;std::string k;double n;
    while(f>>k>>n){if(!std::isfinite(n))throw std::runtime_error("Non-finite parameter");v[k]=n;}
    const char* required[]={"sequence","pixel_width","pixel_height","rows","cols","area_percent","input_nits","background_nits","label"};
    for(auto name:required)if(!v.count(name))throw std::runtime_error(std::string("Missing ")+name);
    for(auto name:{"sequence","pixel_width","pixel_height","rows","cols","label"})if(v[name]!=std::floor(v[name])||v[name]<0||v[name]>100000000)throw std::runtime_error("Invalid integer parameter");
    Config c;c.sequence=int(v["sequence"]);c.pixelWidth=int(v["pixel_width"]);c.pixelHeight=int(v["pixel_height"]);c.rows=int(v["rows"]);c.cols=int(v["cols"]);c.label=int(v["label"]);
    c.area=v["area_percent"];c.nits=v["input_nits"];c.background=v["background_nits"];
    if(c.rows<1||c.rows>64||c.cols<1||c.cols>64||c.area<0||c.area>100||c.nits<0||c.nits>10000||c.background<0||c.background>10000||c.label>1||(bool(c.pixelWidth)!=bool(c.pixelHeight)))throw std::runtime_error("Pattern parameters out of range");
    return c;
}
static void publishReceipt(const fs::path& temp,const fs::path& destination){
    for(int attempt=0;attempt<6;attempt++){
        if(MoveFileExW(temp.c_str(),destination.c_str(),MOVEFILE_REPLACE_EXISTING))return;
        DWORD error=GetLastError();
        if((error!=ERROR_ACCESS_DENIED&&error!=ERROR_SHARING_VIOLATION)||attempt==5)throw std::runtime_error("Cannot publish pixel receipt: "+std::to_string(error));
        Sleep(2*(attempt+1));
    }
}
struct Presentation {HWND window;RECT viewport;unsigned overlaps=0;};
static BOOL CALLBACK overlappingWindow(HWND other,LPARAM data){
    auto& p=*reinterpret_cast<Presentation*>(data);if(other==p.window)return FALSE;
    if(!IsWindowVisible(other)||IsIconic(other))return TRUE;
    // Restrict this check to our controller/pattern windows and the taskbar.
    // A full-screen, per-pixel-transparent capture/cursor overlay has no useful
    // rectangular coverage and must not permanently invalidate every sample.
    wchar_t name[256]={};GetClassNameW(other,name,256);std::wstring cls=name;
    if(cls.rfind(L"MIHDRControlWindow-",0)!=0&&cls!=L"MI_HDR_Control_Pattern"&&cls!=L"Shell_TrayWnd"&&cls!=L"Shell_SecondaryTrayWnd")return TRUE;
    DWORD cloaked=0;if(SUCCEEDED(DwmGetWindowAttribute(other,DWMWA_CLOAKED,&cloaked,sizeof(cloaked)))&&cloaked)return TRUE;
    BYTE alpha=255;DWORD flags=0;COLORREF color=0;
    if((GetWindowLongPtrW(other,GWL_EXSTYLE)&WS_EX_LAYERED)&&GetLayeredWindowAttributes(other,&color,&alpha,&flags)&&(flags&LWA_ALPHA)&&alpha==0)return TRUE;
    RECT r{},intersection{};if(FAILED(DwmGetWindowAttribute(other,DWMWA_EXTENDED_FRAME_BOUNDS,&r,sizeof(r)))||IsRectEmpty(&r))GetWindowRect(other,&r);
    if(IntersectRect(&intersection,&r,&p.viewport))p.overlaps++;
    return TRUE;
}
static void publishPresentation(HWND window,const fs::path& directory,int sequence){
    Presentation p{window,{}};GetClientRect(patternSurface,&p.viewport);MapWindowPoints(patternSurface,nullptr,reinterpret_cast<POINT*>(&p.viewport),2);
    bool visible=IsWindowVisible(window)&&!IsIconic(window);if(visible)EnumWindows(overlappingWindow,reinterpret_cast<LPARAM>(&p));
    FILETIME now;GetSystemTimeAsFileTime(&now);ULARGE_INTEGER t;t.LowPart=now.dwLowDateTime;t.HighPart=now.dwHighDateTime;
    std::ostringstream j;j<<"{\"sequence\":"<<sequence<<",\"visible\":"<<(visible?"true":"false")<<",\"foreground\":"<<(GetAncestor(GetForegroundWindow(),GA_ROOT)==window?"true":"false")<<",\"occluded\":"<<(p.overlaps?"true":"false")<<",\"overlap_windows\":"<<p.overlaps<<",\"occlusion_scope\":\"controller-and-taskbar\",\"windowed\":"<<(previewWindowed?"true":"false")<<",\"wall_time_ms\":"<<t.QuadPart/10000-11644473600000ULL<<"}";
    auto path=directory/L"presentation.json",temp=directory/L"presentation.tmp";
    {std::ofstream f(temp);f<<j.str();if(!f)throw std::runtime_error("Cannot write presentation state");}publishReceipt(temp,path);
}
static std::vector<D3D11_RECT> geometry(const Config& c,int w,int h){
    std::vector<D3D11_RECT> r;
    for(int row=0;row<c.rows;++row)for(int col=0;col<c.cols;++col){
        int left=col*w/c.cols,right=(col+1)*w/c.cols,top=row*h/c.rows,bottom=(row+1)*h/c.rows;
        int pw=c.pixelWidth,ph=c.pixelHeight;
        if(!pw){double s=std::sqrt(c.area/100.);pw=int(std::lround((right-left)*s));ph=int(std::lround((bottom-top)*s));if(c.area>0){pw=std::max(1,pw);ph=std::max(1,ph);}}
        if(pw>right-left||ph>bottom-top)throw std::runtime_error("Pixel window exceeds its array cell; reduce size or rows/columns");
        if(pw&&ph){int x=left+(right-left-pw)/2,y=top+(bottom-top-ph)/2;r.push_back({x,y,x+pw,y+ph});}
    }
    return r;
}
static std::vector<uint32_t> annotation(int w,int h,double foreground,double background,const std::string& text){
    BITMAPINFO info{};info.bmiHeader={sizeof(BITMAPINFOHEADER),w,-h,1,32,BI_RGB};void* bits=nullptr;
    HDC dc=CreateCompatibleDC(nullptr);HBITMAP bm=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&bits,nullptr,0);auto old=SelectObject(dc,bm);
    RECT rect{0,0,w,h};FillRect(dc,&rect,(HBRUSH)GetStockObject(BLACK_BRUSH));SetBkMode(dc,TRANSPARENT);SetTextColor(dc,RGB(255,255,255));
    HFONT font=CreateFontW(-std::max(18,patternUnit(patternSurface,18)),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,ANTIALIASED_QUALITY,DEFAULT_PITCH,L"Microsoft YaHei UI");auto prev=SelectObject(dc,font);
    auto t=wide(text);rect.left=12;rect.top=3;rect.right-=12;DrawTextW(dc,t.c_str(),int(t.size()),&rect,DT_LEFT|DT_SINGLELINE|DT_VCENTER|DT_END_ELLIPSIS);GdiFlush();
    std::vector<uint32_t> out(size_t(w)*h);auto src=static_cast<uint32_t*>(bits);double fg=pq(foreground)*1023,bg=pq(background)*1023;
    for(size_t i=0;i<out.size();++i){double a=double(std::max({src[i]&255U,(src[i]>>8)&255U,(src[i]>>16)&255U}))/255;uint32_t q=uint32_t(std::lround(bg+(fg-bg)*a));out[i]=0xc0000000U|q|(q<<10)|(q<<20);}
    SelectObject(dc,prev);DeleteObject(font);SelectObject(dc,old);DeleteObject(bm);DeleteDC(dc);return out;
}
int wmain(int argc,wchar_t** argv){
    try {
        // config, readback JSON, status text, stop file, mode, duration, monitor index.
        if(argc<8)throw std::runtime_error("Usage: hdr-pattern-control config.txt check.json status.txt stop-file fullscreen|windowed|check-only seconds [monitor-index]");
        fs::path configPath=argv[1],logPath=argv[2],statusPath=argv[3],stopPath=argv[4];std::wstring mode=argv[5];double seconds=std::stod(argv[6]);int display=std::stoi(argv[7]);
        bool hidden=mode==L"check-only"||mode==L"check-live",windowed=mode==L"windowed";previewWindowed=windowed;patternHidden=hidden;
        if(!hidden&&!windowed&&mode!=L"fullscreen")throw std::runtime_error("Unknown display mode");
        if(!std::isfinite(seconds)||seconds<0||seconds>86400)throw std::runtime_error("Invalid duration");
        SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);EnumDisplayMonitors(nullptr,nullptr,enumMonitor,0);
        if(display<0||display>=int(monitors.size()))throw std::runtime_error("Monitor index unavailable");
        MONITORINFO mi{sizeof(mi)};GetMonitorInfoW(monitors[display],&mi);int width=mi.rcMonitor.right-mi.rcMonitor.left,height=mi.rcMonitor.bottom-mi.rcMonitor.top;patternMonitor=mi.rcMonitor;previewRestore={mi.rcMonitor.left+40,mi.rcMonitor.top+40,mi.rcMonitor.left+std::min(1280,width),mi.rcMonitor.top+std::min(800,height)};
        WNDCLASSW wc{};wc.lpfnWndProc=wndproc;wc.hInstance=GetModuleHandleW(nullptr);wc.lpszClassName=L"MI_HDR_Control_Pattern";wc.hCursor=LoadCursor(nullptr,IDC_ARROW);RegisterClassW(&wc);
        HWND window=CreateWindowExW(0,wc.lpszClassName,L"MI HDR pattern | Esc exits",windowed?(WS_POPUP|WS_THICKFRAME|WS_MINIMIZEBOX|WS_MAXIMIZEBOX|WS_SYSMENU|WS_CLIPCHILDREN):WS_POPUP,mi.rcMonitor.left,mi.rcMonitor.top,windowed?std::min(1280,width):width,windowed?std::min(800,height):height,nullptr,nullptr,wc.hInstance,nullptr);
        if(!window)throw std::runtime_error("CreateWindow failed");
        WNDCLASSW surfaceClass{};surfaceClass.lpfnWndProc=DefWindowProcW;surfaceClass.hInstance=wc.hInstance;surfaceClass.lpszClassName=L"MI_HDR_Pattern_Surface";surfaceClass.hCursor=LoadCursor(nullptr,IDC_ARROW);RegisterClassW(&surfaceClass);
        patternSurface=CreateWindowW(surfaceClass.lpszClassName,L"HDR viewport",WS_CHILD|WS_VISIBLE|WS_CLIPSIBLINGS,0,0,width,height,window,nullptr,wc.hInstance,nullptr);
        if(!patternSurface)throw std::runtime_error("Create HDR viewport failed");HWND tips=CreateWindowExW(WS_EX_TOPMOST,TOOLTIPS_CLASSW,nullptr,WS_POPUP|TTS_ALWAYSTIP,0,0,0,0,window,nullptr,wc.hInstance,nullptr);
        static wchar_t tipText[5][80]={L"置顶 / 取消置顶图样",L"最小化图样",L"窗口最大化 / 还原（不是无栏全屏）",L"进入 / 退出无栏全屏",L"关闭图样；不退出工作台"};
        for(int i=0;i<5;i++){TOOLINFOW ti={sizeof(ti)};ti.uFlags=TTF_IDISHWND|TTF_SUBCLASS;ti.hwnd=window;ti.uId=reinterpret_cast<UINT_PTR>(patternButtons[i]);ti.lpszText=tipText[i];SendMessageW(tips,TTM_ADDTOOLW,0,reinterpret_cast<LPARAM>(&ti));}
        positionPatternButtons(window);if(!hidden)createPatternButtons(window);
        const int desktopWidth=width,desktopHeight=height;RECT viewport;GetClientRect(patternSurface,&viewport);width=viewport.right;height=viewport.bottom;
        ComPtr<IDXGIFactory2> factory;check(CreateDXGIFactory1(IID_PPV_ARGS(&factory)),"DXGI factory");
        ComPtr<IDXGIAdapter1> selected;
        for(UINT a=0;;++a){ComPtr<IDXGIAdapter1> ad;if(factory->EnumAdapters1(a,&ad)==DXGI_ERROR_NOT_FOUND)break;for(UINT o=0;;++o){ComPtr<IDXGIOutput> output;if(ad->EnumOutputs(o,&output)==DXGI_ERROR_NOT_FOUND)break;DXGI_OUTPUT_DESC d{};output->GetDesc(&d);if(d.Monitor==monitors[display])selected=ad;}}
        if(!selected)throw std::runtime_error("No graphics adapter for selected monitor");
        ComPtr<ID3D11Device> device;ComPtr<ID3D11DeviceContext> context;ComPtr<ID3D11DeviceContext1> ctx;
        check(D3D11CreateDevice(selected.Get(),D3D_DRIVER_TYPE_UNKNOWN,nullptr,0,nullptr,0,D3D11_SDK_VERSION,&device,nullptr,&context),"D3D11 device");check(context.As(&ctx),"D3D11.1 context");
        DXGI_SWAP_CHAIN_DESC1 desc{};desc.Width=width;desc.Height=height;desc.Format=DXGI_FORMAT_R10G10B10A2_UNORM;desc.SampleDesc.Count=1;desc.BufferUsage=DXGI_USAGE_RENDER_TARGET_OUTPUT;desc.BufferCount=2;desc.SwapEffect=DXGI_SWAP_EFFECT_FLIP_DISCARD;desc.Flags=DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT;
        ComPtr<IDXGISwapChain1> chain1;ComPtr<IDXGISwapChain4> chain;
        check(factory->CreateSwapChainForHwnd(device.Get(),patternSurface,&desc,nullptr,nullptr,&chain1),"Swap chain");check(chain1.As(&chain),"DXGI 1.5");factory->MakeWindowAssociation(window,DXGI_MWA_NO_ALT_ENTER);check(chain->SetMaximumFrameLatency(1),"Frame latency");patternFrameReady=chain->GetFrameLatencyWaitableObject();if(!patternFrameReady)throw std::runtime_error("Frame latency handle unavailable");
        UINT support=0;check(chain->CheckColorSpaceSupport(DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020,&support),"PQ support");if(!(support&DXGI_SWAP_CHAIN_COLOR_SPACE_SUPPORT_FLAG_PRESENT))throw std::runtime_error("PQ presentation unavailable");
        check(chain->SetColorSpace1(DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020),"PQ BT.2020");
        ComPtr<IDXGIOutput> output;ComPtr<IDXGIOutput6> output6;DXGI_OUTPUT_DESC1 od{};check(chain->GetContainingOutput(&output),"Output");check(output.As(&output6),"Output6");check(output6->GetDesc1(&od),"Output description");
        if(od.ColorSpace!=DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020)throw std::runtime_error("Windows HDR is off on selected monitor");
        ComPtr<ID3D11Texture2D> buffer,staging,footer;ComPtr<ID3D11RenderTargetView> target;
        auto createTargets=[&](){check(chain->GetBuffer(0,IID_PPV_ARGS(&buffer)),"Buffer");check(device->CreateRenderTargetView(buffer.Get(),nullptr,&target),"Target");D3D11_TEXTURE2D_DESC sd{};buffer->GetDesc(&sd);sd.Usage=D3D11_USAGE_STAGING;sd.BindFlags=0;sd.CPUAccessFlags=D3D11_CPU_ACCESS_READ;check(device->CreateTexture2D(&sd,nullptr,&staging),"Readback staging");};createTargets();
        DEVMODEW displayMode={};displayMode.dmSize=sizeof(displayMode);EnumDisplaySettingsW(od.DeviceName,ENUM_CURRENT_SETTINGS,&displayMode);uint64_t presentCount=0,presentStarted=GetTickCount64();
        Config current;current.sequence=-1;std::vector<D3D11_RECT> rects;std::vector<uint32_t> footerData;std::vector<uint8_t> mask(size_t(width)*height);std::string currentStatus;int footerHeight=std::min(height,std::max(28,patternUnit(window,28)));uint64_t geometryPixels=0,changedAt=0,resizedAt=0;bool needsVerify=false,needsPresent=true;
        auto draw=[&](){float bg=float(pq(current.background)),fg=float(pq(current.nits));const float black[]={bg,bg,bg,1},white[]={fg,fg,fg,1};context->ClearRenderTargetView(target.Get(),black);if(!rects.empty())ctx->ClearView(target.Get(),white,rects.data(),UINT(rects.size()));if(footer)context->CopySubresourceRegion(buffer.Get(),0,0,0,0,footer.Get(),0,nullptr);};
        auto verify=[&](){
            context->CopyResource(staging.Get(),buffer.Get());D3D11_MAPPED_SUBRESOURCE mapped{};check(context->Map(staging.Get(),0,D3D11_MAP_READ,0,&mapped),"Readback");uint64_t wrong=0,lit=0;uint32_t fg=packed(current.nits),bg=packed(current.background);
            for(int y=0;y<height;++y){auto row=reinterpret_cast<const uint32_t*>(static_cast<const char*>(mapped.pData)+y*mapped.RowPitch);for(int x=0;x<width;++x){uint32_t wanted=mask[size_t(y)*width+x]?fg:bg;if(footer&&y<footerHeight)wanted=footerData[size_t(y)*width+x];wrong+=(row[x]&0x3fffffff)!=(wanted&0x3fffffff);lit+=(row[x]&0x3fffffff)!=0;}}
            context->Unmap(staging.Get(),0);if(wrong)throw std::runtime_error("GPU pixel mismatch: "+std::to_string(wrong));
            std::ostringstream j;j<<std::setprecision(12)<<"{\"sequence\":"<<current.sequence<<",\"width\":"<<width<<",\"height\":"<<height<<",\"rows\":"<<current.rows<<",\"cols\":"<<current.cols<<",\"patch_count\":"<<rects.size()<<",\"first_patch_width\":"<<(rects.empty()?0:rects[0].right-rects[0].left)<<",\"first_patch_height\":"<<(rects.empty()?0:rects[0].bottom-rects[0].top)<<",\"requested_area_percent\":"<<current.area<<",\"geometric_pixels\":"<<geometryPixels<<",\"actual_area_percent\":"<<100.*geometryPixels/(size_t(desktopWidth)*desktopHeight)<<",\"viewport_area_percent\":"<<100.*geometryPixels/(size_t(width)*height)<<",\"desktop_width\":"<<desktopWidth<<",\"desktop_height\":"<<desktopHeight<<",\"lit_pixels_including_annotation\":"<<lit<<",\"wrong_pixels\":"<<wrong<<",\"input_nits\":"<<current.nits<<",\"code10\":"<<(packed(current.nits)&1023)<<",\"background_nits\":"<<current.background<<",\"annotation\":"<<(patternAnnotationVisible(current.label)?"true":"false")<<",\"windowed_preview\":"<<(previewWindowed?"true":"false")<<",\"physical_pixel_mapping\":"<<"true"<<",\"titlebar_visible\":"<<(previewWindowed?"true":"false")<<",\"output_bits_per_color\":"<<od.BitsPerColor<<",\"output_color_space\":"<<int(od.ColorSpace)<<",\"configured_refresh_hz\":"<<displayMode.dmDisplayFrequency<<",\"present_fps\":"<<presentCount*1000./std::max<uint64_t>(1,GetTickCount64()-presentStarted)<<",\"scheduler\":\"DXGI frame-latency event\",\"status\":\""<<escaped(currentStatus)<<"\"}";
            auto temp=logPath;temp+=L".tmp";{std::ofstream f(temp);f<<j.str();if(!f)throw std::runtime_error("Cannot write pixel receipt");}publishReceipt(temp,logPath);auto history=logPath;history+=L".jsonl";std::ofstream(history,std::ios::app)<<j.str()<<"\n";
        };
        uint64_t configPollAt=0;
        auto update=[&](){
            if(!patternViewChanged&&GetTickCount64()-configPollAt<20)return;configPollAt=GetTickCount64();
            Config next=readConfig(configPath);std::string status=sharedText(statusPath,false);
            bool changed=next.sequence!=current.sequence||patternViewChanged;
            if(!changed&&status==currentStatus)return;
            patternViewChanged=false;current=next;currentStatus=status;needsPresent=true;
            if(changed){
                changedAt=GetTickCount64();needsVerify=true;
                rects=geometry(current,width,height);std::fill(mask.begin(),mask.end(),0);geometryPixels=0;
                for(auto r:rects){geometryPixels+=uint64_t(r.right-r.left)*(r.bottom-r.top);for(int y=r.top;y<r.bottom;++y)std::fill(mask.begin()+size_t(y)*width+r.left,mask.begin()+size_t(y)*width+r.right,1);}
                DXGI_HDR_METADATA_HDR10 metadata{{35400,14600},{8500,39850},{6550,2300},{15635,16450},10000,1,10000,10000};check(chain->SetHDRMetaData(DXGI_HDR_METADATA_TYPE_HDR10,sizeof(metadata),&metadata),"HDR metadata");
            }
            footer.Reset();if(patternAnnotationVisible(current.label)){
                bool full=geometryPixels==uint64_t(width)*height;double bg=full?current.nits:current.background,fg=bg>=1?bg*.65:bg+1;
                footerData=annotation(width,footerHeight,fg,bg,status);D3D11_TEXTURE2D_DESC fd{};fd.Width=width;fd.Height=footerHeight;fd.MipLevels=1;fd.ArraySize=1;fd.Format=DXGI_FORMAT_R10G10B10A2_UNORM;fd.SampleDesc.Count=1;fd.Usage=D3D11_USAGE_IMMUTABLE;fd.BindFlags=D3D11_BIND_SHADER_RESOURCE;D3D11_SUBRESOURCE_DATA init{footerData.data(),UINT(width*4),0};check(device->CreateTexture2D(&fd,&init,&footer),"Annotation");
            }
        };
        update();if(mode==L"check-only"){WaitForSingleObject(patternFrameReady,1000);draw();verify();CloseHandle(patternFrameReady);patternFrameReady=nullptr;DestroyWindow(window);return 0;}
        auto start=GetTickCount64();uint64_t presentationAt=0;
        patternTick=[&](){
            if(fs::exists(stopPath)||(seconds>0&&GetTickCount64()-start>=seconds*1000)){DestroyWindow(window);return;}
            if(!hidden&&GetTickCount64()-presentationAt>=250){publishPresentation(window,logPath.parent_path(),current.sequence);presentationAt=GetTickCount64();}
            if(IsIconic(window))return;
            RECT view;GetClientRect(patternSurface,&view);int w=view.right,h=view.bottom;
            if(w>0&&h>0&&(w!=width||h!=height)&&(!patternSizing||GetTickCount64()-resizedAt>=64)){
                context->ClearState();target.Reset();buffer.Reset();staging.Reset();footer.Reset();
                check(chain->ResizeBuffers(0,w,h,DXGI_FORMAT_UNKNOWN,DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT),"Resize HDR viewport");width=w;height=h;createTargets();mask.resize(size_t(width)*height);footerHeight=std::min(height,std::max(28,patternUnit(window,28)));patternViewChanged=true;resizedAt=GetTickCount64();
            }
            update();
            if(hidden||patternFrameAllowed||needsPresent){draw();HRESULT hr=chain->Present(hidden?0:1,DXGI_PRESENT_DO_NOT_WAIT);if(hr!=DXGI_ERROR_WAS_STILL_DRAWING){check(hr,"Present");if(hr==S_OK){presentCount++;needsPresent=false;}}}
            if(needsVerify&&!patternSizing&&GetTickCount64()-changedAt>=120){draw();verify();needsVerify=false;}
        };
        if(!hidden){ShowWindow(window,SW_SHOW);if(!windowed)SetWindowPos(window,HWND_TOP,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE);SetForegroundWindow(window);}
        SetTimer(window,5200,10,nullptr);MSG message{};bool running=true;
        while(running&&IsWindow(window)){
            DWORD ready=MsgWaitForMultipleObjectsEx(1,&patternFrameReady,100,QS_ALLINPUT,MWMO_INPUTAVAILABLE);
            while(PeekMessageW(&message,nullptr,0,0,PM_REMOVE)){if(message.message==WM_QUIT){running=false;break;}if(!previewWindowed&&patternMenuKey(message.message,message.wParam)){SendMessageW(window,message.message,message.wParam,message.lParam);continue;}if(message.message==WM_KEYDOWN&&message.wParam==VK_ESCAPE){SendMessageW(window,WM_CLOSE,0,0);continue;}TranslateMessage(&message);DispatchMessageW(&message);}
            if(running&&IsWindow(window)&&ready==WAIT_OBJECT_0){patternFrameAllowed=true;SendMessageW(window,WM_TIMER,5200,0);}
        }
        patternTick=nullptr;CloseHandle(patternFrameReady);patternFrameReady=nullptr;if(!patternFailure.empty())throw std::runtime_error(patternFailure);
        std::cout<<"pattern_stopped=1\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}
}
