"""Create or remove Decypher startup entries."""

import os
import sys


STARTUP_DIR_PARTS = ("Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def startup_folder() -> str:
    return os.path.join(os.environ["APPDATA"], *STARTUP_DIR_PARTS)


def setup_startup():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    vbs_path = os.path.join(startup_folder(), "run_decypher.vbs")

    pythonw = os.path.join(script_dir, "venv", "Scripts", "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = "pythonw"  # fallback to PATH if no venv

    vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "{script_dir}"
WshShell.Run "{pythonw} overlay.py", 0, False
'''

    with open(vbs_path, "w") as f:
        f.write(vbs_content)

    print(f"Startup entry created at:\n{vbs_path}")
    print("\nDecypher will now run automatically on Windows startup.")


def remove_startup():
    removed = False
    for filename in ("run_decypher.vbs", "Decypher.lnk"):
        path = os.path.join(startup_folder(), filename)
        if os.path.exists(path):
            os.remove(path)
            removed = True

    if removed:
        print("Startup entry removed.")
    else:
        print("No startup entry found.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--remove":
        remove_startup()
    else:
        setup_startup()
