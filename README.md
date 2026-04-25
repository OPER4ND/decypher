# Decypher

Lightweight Valorant overlay focused on two features:

- Agent select actions: select, instalock, and dodge.
- Mute on Death: mute the whole Valorant audio session when the death strip is detected, then unmute when the live round score changes.

Decypher does not resolve hidden IGNs, ranks, peak ranks, or party data.

## Requirements

- Windows
- Valorant in borderless windowed mode
- Python 3.10+ for source installs

## Run From Source

```powershell
pip install -r requirements.txt
python overlay.py
```

Or use:

```bat
install.bat
```

## Build

```powershell
python -m PyInstaller decypher.spec --noconfirm
```

The executable is written to `dist\decypher.exe`.

## Install Built EXE

After building or downloading a release package, run:

```bat
install_exe.bat
```

## Controls

- `Mute on Death`: arms or disables strip-based mute automation.
- `F2`: toggle overlay visibility while in match.
- `F3`: toggle click-through mode.
- `Esc`: close the overlay.

## Optional Script

`dragnscroll.ahk` is included in the repo for drag-to-scroll behavior. Decypher starts and stops it automatically while VALORANT is running, focused, and not in a live match. This requires AutoHotkey v2 to be installed; if AutoHotkey is missing, Decypher simply skips the script.

## Behavior

When `Mute on Death` is enabled, Decypher samples a narrow fixed strip of the Valorant window. A matching death-strip color mutes the Valorant audio session. While muted, Decypher polls the local presence score and unmutes when the total score changes.

If the death strip is already detected when `Mute on Death` is enabled, Decypher treats that as an existing death state, does not mute, waits for the next score change, then applies a 25 second round-start cooldown before arming again.

## Uninstall

Run:

```bat
uninstall.bat
```

Or delete the Decypher shortcut from:

```text
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
```
