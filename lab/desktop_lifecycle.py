"""Desktop-owned lifetime and PC-only preferences. No device parameter API here."""
import ctypes
import json
import os
import threading
import time
from pathlib import Path
from http.server import ThreadingHTTPServer

DEFAULT_UI={'theme':'dark','auto_connect':False,'quick_tune':True,'unit':'mono','sidebar_collapsed':False,'chart_axis':'log','ui_scale':'auto'}

def preferences(value):
    result={**DEFAULT_UI,**value}
    if result['theme'] not in ('light','dark','system'):raise ValueError('未知界面主题')
    if result['unit'] not in ('unit01','unit00','unit02','unit08','mark06','mono'):raise ValueError('未知配色主题')
    if result['chart_axis'] not in ('linear','log'):raise ValueError('未知曲线横轴')
    if result['ui_scale'] not in ('auto','100','95','90','75','65','50'):raise ValueError('界面比例仅支持自动/100/95/90/75/65/50%')
    if any(type(result[k]) is not bool for k in ('auto_connect','quick_tune','sidebar_collapsed')):raise ValueError('便民选项必须为开关')
    if set(result)!=set(DEFAULT_UI):raise ValueError('未知便民选项')
    return result

class ManagedServer(ThreadingHTTPServer):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.stop_lock=threading.Lock();self.stopping=False

    def stop_controller(self,reason):
        with self.stop_lock:
            if self.stopping:return
            self.stopping=True
        try:self.bridge.close_controller(reason)
        finally:self.shutdown()

def watch_owner(server):
    pid=int(os.environ.get('MI_DESKTOP_OWNER_PID','0'))
    if not pid:return
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]
    kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x100000,False,pid)
    def wait():
        if handle:
            while kernel.WaitForSingleObject(handle,2000)==0x102:
                # A minimized/throttled WebView must not end an otherwise live desktop session.
                server.bridge.beat=time.monotonic()
            kernel.CloseHandle(handle)
        server.stop_controller('desktop-owner-exited')
    threading.Thread(target=wait,daemon=True).start()
