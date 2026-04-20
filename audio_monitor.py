"""Live audio session peak monitor — shows which processes are making noise."""

import time
import os
import datetime
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

POLL_INTERVAL = 0.1
THRESHOLD = 0.01  # ignore near-silent sessions
LOG_FILE = "audio_monitor.log"


def get_sessions():
    try:
        return AudioUtilities.GetAllSessions()
    except Exception:
        return []


def peak(session):
    try:
        meter = session._ctl.QueryInterface(IAudioMeterInformation)
        return meter.GetPeakValue()
    except Exception:
        return 0.0


def name(session):
    p = getattr(session, "Process", None)
    return p.name() if p else "(system)"


def bar(value, width=20):
    filled = int(value * width)
    return "[" + "#" * filled + "-" * (width - filled) + f"] {value:.3f}"


with open(LOG_FILE, "a", encoding="utf-8") as f:
    f.write(f"\n=== session started {datetime.datetime.now()} ===\n")

while True:
    os.system("cls")
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    sessions = get_sessions()
    active = [(name(s), peak(s)) for s in sessions]
    active.sort(key=lambda x: -x[1])
    print(f"{'PROCESS':<35} PEAK")
    print("-" * 60)
    noisy = []
    for n, p in active:
        marker = " <--" if p > THRESHOLD else ""
        print(f"{n:<35} {bar(p)}{marker}")
        if p > THRESHOLD:
            noisy.append(f"{n}={p:.3f}")
    if noisy:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {', '.join(noisy)}\n")
    time.sleep(POLL_INTERVAL)
