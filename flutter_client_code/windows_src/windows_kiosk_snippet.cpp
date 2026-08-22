// Add these includes to windows/runner/flutter_window.cpp
#include <windows.h>

/* 
   INSTRUCTIONS:
   1. Open windows/runner/flutter_window.cpp
   2. Locate the FlutterWindow::OnCreate method.
   3. Add the following code inside OnCreate to make the window TopMost and block keys.
*/

// --- SNIPPET START ---

// 1. Force Fullscreen and Always on Top
HWND hwnd = GetHandle();
SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE);

// 2. Remove standard window controls (Maximize, Minimize) for Kiosk feel
LONG lStyle = GetWindowLong(hwnd, GWL_STYLE);
lStyle &= ~(WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU);
SetWindowLong(hwnd, GWL_STYLE, lStyle);

// 3. Force maximize
ShowWindow(hwnd, SW_MAXIMIZE);

// --- SNIPPET END ---


/* 
   ADVANCED: BLOCKING ALT+TAB, CTRL+ESC, WIN KEY
   This requires a LowLevelKeyboardProc hook.
   Add this to windows/runner/main.cpp main() function or a separate helper.
*/

HHOOK hHook = SetWindowsHookEx(WH_KEYBOARD_LL, LowLevelKeyboardProc, GetModuleHandle(NULL), 0);

LRESULT CALLBACK LowLevelKeyboardProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode == HC_ACTION) {
        KBDLLHOOKSTRUCT* pKey = (KBDLLHOOKSTRUCT*)lParam;
        
        // Detect WIN key
        if (pKey->vkCode == VK_LWIN || pKey->vkCode == VK_RWIN) return 1;
        
        // Detect ALT+TAB
        if (pKey->vkCode == VK_TAB && (pKey->flags & LLKHF_ALTDOWN)) return 1;
        
        // Detect CTRL+ESC
        if (pKey->vkCode == VK_ESCAPE && (GetAsyncKeyState(VK_CONTROL) & 0x8000)) return 1;
    }
    return CallNextHookEx(NULL, nCode, wParam, lParam);
}
