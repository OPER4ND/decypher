"""Create or remove Decypher startup entries."""

import os
import subprocess
import sys


STARTUP_DIR_PARTS = ("Microsoft", "Windows", "Start Menu", "Programs", "Startup")
STARTUP_ENTRY_NAMES = ("run_decypher.vbs", "Decypher.lnk")


def startup_folder() -> str:
    return os.path.join(os.environ["APPDATA"], *STARTUP_DIR_PARTS)


def script_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def source_entrypoint_path() -> str:
    return os.path.join(script_dir(), "overlay.py")


def resolve_source_pythonw() -> str:
    root = script_dir()
    pyvenv_cfg = os.path.join(root, "venv", "pyvenv.cfg")

    try:
        with open(pyvenv_cfg, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                key, _, value = raw_line.partition("=")
                if key.strip().lower() != "home":
                    continue
                candidate = os.path.join(value.strip(), "pythonw.exe")
                if os.path.exists(candidate):
                    return candidate
    except OSError:
        pass

    base_prefix = getattr(sys, "base_prefix", "")
    if base_prefix:
        candidate = os.path.join(base_prefix, "pythonw.exe")
        if os.path.exists(candidate):
            return candidate

    return "pythonw"


def remove_startup_entries() -> bool:
    removed = False
    for filename in STARTUP_ENTRY_NAMES:
        path = os.path.join(startup_folder(), filename)
        if os.path.exists(path):
            os.remove(path)
            removed = True
    return removed


def setup_startup():
    root = script_dir()
    vbs_path = os.path.join(startup_folder(), "run_decypher.vbs")

    # Clear stale startup entries so source installs and release installs
    # cannot leave competing launchers behind.
    remove_startup_entries()

    pythonw = resolve_source_pythonw()
    entrypoint = source_entrypoint_path()

    vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "{root}"
WshShell.Run """{pythonw}"" ""{entrypoint}""", 0, False
'''

    with open(vbs_path, "w") as f:
        f.write(vbs_content)

    print(f"Startup entry created at:\n{vbs_path}")
    print("\nDecypher will now run automatically on Windows startup.")


def remove_startup():
    if remove_startup_entries():
        print("Startup entry removed.")
    else:
        print("No startup entry found.")


def launch_source_now():
    subprocess.Popen(
        [resolve_source_pythonw(), source_entrypoint_path()],
        cwd=script_dir(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--remove":
        remove_startup()
    elif len(sys.argv) > 1 and sys.argv[1] == "--launch":
        launch_source_now()
    else:
        setup_startup()
