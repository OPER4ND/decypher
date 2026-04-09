"""
Setup Decypher to run on Windows startup
"""

import os
import sys

def setup_startup():
    # Get paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    startup_folder = os.path.join(
        os.environ["APPDATA"],
        "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )
    vbs_path = os.path.join(startup_folder, "run_decypher.vbs")

    # Create VBS script that runs silently
    vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "{script_dir}"
WshShell.Run "pythonw overlay.py", 0, False
'''

    with open(vbs_path, "w") as f:
        f.write(vbs_content)

    print(f"Startup entry created at:\n{vbs_path}")
    print("\nDecypher will now run automatically on Windows startup.")


def remove_startup():
    startup_folder = os.path.join(
        os.environ["APPDATA"],
        "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )
    vbs_path = os.path.join(startup_folder, "run_decypher.vbs")

    if os.path.exists(vbs_path):
        os.remove(vbs_path)
        print("Startup entry removed.")
    else:
        print("No startup entry found.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--remove":
        remove_startup()
    else:
        setup_startup()
