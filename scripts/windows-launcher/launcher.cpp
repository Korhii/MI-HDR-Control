#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <string>

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    wchar_t path[32768];
    DWORD n = GetModuleFileNameW(nullptr, path, 32768);
    if (!n || n >= 32768) return 1;
    std::wstring root(path, n);
    root.resize(root.find_last_of(L"\\/"));
    std::wstring python = root + L"\\tools\\python\\pythonw.exe";
    std::wstring command = L"\"" + python + L"\" \"" + root + L"\\lab\\launch.py\"";
    STARTUPINFOW startup = {sizeof(startup)};
    PROCESS_INFORMATION process = {};
    if (!CreateProcessW(python.c_str(), command.data(), nullptr, nullptr, FALSE,
                        CREATE_NO_WINDOW, nullptr, root.c_str(), &startup, &process)) {
        MessageBoxW(nullptr, L"无法启动。请先完整解压便携包，保留 tools 和 lab 目录。",
                    L"MI HDR Control", MB_OK | MB_ICONERROR);
        return 1;
    }
    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD result = 1;
    GetExitCodeProcess(process.hProcess, &result);
    CloseHandle(process.hProcess);
    return static_cast<int>(result);
}
