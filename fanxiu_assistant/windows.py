"""Small native Windows process/window helpers; no external runtime required."""
import ctypes
from ctypes import wintypes as w
from pathlib import Path
import os


def process_images():
    if os.name != 'nt':
        return []
    class Entry(ctypes.Structure):
        _fields_ = [('size', w.DWORD), ('usage', w.DWORD), ('pid', w.DWORD),
                    ('heap', ctypes.c_size_t), ('module', w.DWORD), ('threads', w.DWORD),
                    ('parent', w.DWORD), ('priority', w.LONG), ('flags', w.DWORD), ('exe', w.WCHAR * 260)]
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.CreateToolhelp32Snapshot.restype = w.HANDLE
    k.OpenProcess.restype = w.HANDLE
    k.CloseHandle.argtypes = [w.HANDLE]
    k.Process32FirstW.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]
    k.Process32NextW.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]
    k.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
    snapshot = k.CreateToolhelp32Snapshot(2, 0)
    if snapshot == w.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(), '无法读取进程列表')
    rows, entry = [], Entry()
    entry.size = ctypes.sizeof(entry)
    try:
        more = k.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            if entry.exe.casefold() == 'run.exe':
                handle = k.OpenProcess(0x1000, False, entry.pid)
                if handle:
                    try:
                        path, size = ctypes.create_unicode_buffer(32768), w.DWORD(32768)
                        if k.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                            rows.append((int(entry.pid), Path(path.value)))
                    finally:
                        k.CloseHandle(handle)
            more = k.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        k.CloseHandle(snapshot)
    return rows


def close_window(pid):
    user = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.IsWindowVisible.argtypes = [w.HWND]
    user.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    closed = []
    @callback_type
    def visit(window, _):
        owner = w.DWORD()
        user.GetWindowThreadProcessId(window, ctypes.byref(owner))
        if owner.value == pid and user.IsWindowVisible(window):
            user.PostMessageW(window, 0x10, 0, 0)  # WM_CLOSE; never terminate the process.
            closed.append(True)
        return True
    user.EnumWindows(visit, 0)
    return bool(closed)


def listener_process(port):
    """Resolve only the IPv4 loopback listener; never enumerate unrelated app windows."""
    import socket
    api = ctypes.WinDLL('iphlpapi', use_last_error=True)
    size = w.DWORD(0)
    api.GetExtendedTcpTable(None, ctypes.byref(size), False, 2, 3, 0)
    buffer = ctypes.create_string_buffer(size.value)
    if api.GetExtendedTcpTable(buffer, ctypes.byref(size), False, 2, 3, 0):
        raise OSError('无法确认旧助手监听进程')
    count = ctypes.cast(buffer, ctypes.POINTER(w.DWORD))[0]
    matches=[]
    for index in range(count):
        row=(w.DWORD*6).from_buffer(buffer, 4+index*24)
        if row[0]==2 and row[1]==0x0100007f and socket.ntohs(row[2]&0xffff)==port:
            matches.append(int(row[5]))
    if len(set(matches))!=1:raise RuntimeError('无法唯一确认旧助手，未结束任何进程')
    pid=matches[0]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=w.HANDLE
    kernel.CloseHandle.argtypes=[w.HANDLE]
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:raise OSError('无法读取旧助手路径')
    try:
        kernel.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,ctypes.POINTER(w.DWORD)]
        path=ctypes.create_unicode_buffer(32768);length=w.DWORD(32768)
        if not kernel.QueryFullProcessImageNameW(handle,0,path,ctypes.byref(length)):raise OSError('无法确认旧助手路径')
        return pid,Path(path.value)
    finally:kernel.CloseHandle(handle)


def end_helper_process(pid, expected_image):
    # Recheck on the same handle before terminating only this verified helper process.
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=w.HANDLE
    kernel.CloseHandle.argtypes=[w.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,ctypes.POINTER(w.DWORD)]
    kernel.TerminateProcess.argtypes=[w.HANDLE,w.UINT]
    handle=kernel.OpenProcess(0x1001,False,pid)
    if not handle:raise OSError('无法接替旧助手进程')
    try:
        path=ctypes.create_unicode_buffer(32768);length=w.DWORD(32768)
        if not kernel.QueryFullProcessImageNameW(handle,0,path,ctypes.byref(length)) or Path(path.value).resolve()!=Path(expected_image).resolve():
            raise RuntimeError('旧助手进程身份变化，未结束进程')
        if not kernel.TerminateProcess(handle,0):raise OSError('无法结束旧助手进程')
    finally:kernel.CloseHandle(handle)
