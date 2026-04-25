"""Source entrypoint for Decypher."""
import atexit
import ctypes
import os
import site
import sys

def _add_local_venv_site_packages():
    if getattr(sys, 'frozen', False):
        return
    script_dir = os.path.dirname(os.path.abspath(__file__))
    site_packages = os.path.join(script_dir, 'venv', 'Lib', 'site-packages')
    if os.path.isdir(site_packages):
        site.addsitedir(site_packages)
_add_local_venv_site_packages()
from decypher.app.overlay import DecypherOverlay
_instance_mutex = None

def _acquire_single_instance() -> bool:
    global _instance_mutex
    try:
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        user32 = ctypes.WinDLL('user32', use_last_error=True)
    except Exception:
        return True
    mutex_name = 'Local\\DECYPHER_SINGLE_INSTANCE'
    handle = kernel32.CreateMutexW(None, False, mutex_name)
    if not handle:
        return True
    error = ctypes.get_last_error()
    if error == 183:
        user32.MessageBoxW(None, 'decypher is already running.', 'decypher', 64)
        kernel32.CloseHandle(handle)
        return False
    _instance_mutex = handle
    atexit.register(lambda: kernel32.CloseHandle(_instance_mutex) if _instance_mutex else None)
    return True
if __name__ == '__main__':
    if _acquire_single_instance():
        DecypherOverlay().run()
