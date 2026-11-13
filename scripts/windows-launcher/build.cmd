@echo off
setlocal
if defined VCToolsInstallDir goto build
if defined MI_VCVARS call "%MI_VCVARS%" >nul
if defined VCToolsInstallDir goto build
for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -prerelease -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSROOT=%%i"
if not defined VSROOT (echo Run in an x64 Native Tools Command Prompt or install Visual Studio C++ build tools. & exit /b 1)
call "%VSROOT%\VC\Auxiliary\Build\vcvars64.bat" >nul
:build
if errorlevel 1 exit /b 1
pushd "%~dp0"
rc /nologo /fo launcher.res launcher.rc
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /MT /EHsc /utf-8 desktop.cpp /Fe"..\..\MI HDR Control.exe" /Folauncher.obj /link /SUBSYSTEM:WINDOWS user32.lib gdi32.lib gdiplus.lib advapi32.lib dwmapi.lib shell32.lib ole32.lib oleaut32.lib version.lib shlwapi.lib comctl32.lib comdlg32.lib webview2\WebView2LoaderStatic.lib launcher.res
set result=%errorlevel%
popd
exit /b %result%
