"""Performance monitor — measures CPU, GPU, network, and ImageGrab cost of Decypher."""

import time
import threading
import statistics
import ctypes
import psutil

try:
    import GPUtil
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False

try:
    from PIL import ImageGrab
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

DURATION_SECONDS = 30
SAMPLE_INTERVAL  = 0.25  # seconds between system samples
GRAB_INTERVAL    = 0.25  # simulate the 250ms detection loop

process = psutil.Process()

results = {
    "cpu_pct":       [],
    "ram_mb":        [],
    "net_sent_kb":   [],
    "net_recv_kb":   [],
    "grab_ms":       [],
    "gpu_load_pct":  [],
    "gpu_mem_mb":    [],
}

stop_flag = threading.Event()


def sample_system():
    prev_net = psutil.net_io_counters()
    prev_time = time.time()
    while not stop_flag.is_set():
        time.sleep(SAMPLE_INTERVAL)
        now = time.time()
        elapsed = now - prev_time
        cpu = process.cpu_percent(interval=None)
        ram = process.memory_info().rss / 1024 / 1024
        net = psutil.net_io_counters()
        sent_kb = (net.bytes_sent - prev_net.bytes_sent) / 1024 / elapsed
        recv_kb = (net.bytes_recv - prev_net.bytes_recv) / 1024 / elapsed
        results["cpu_pct"].append(cpu)
        results["ram_mb"].append(ram)
        results["net_sent_kb"].append(sent_kb)
        results["net_recv_kb"].append(recv_kb)
        if GPU_AVAILABLE:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    results["gpu_load_pct"].append(gpus[0].load * 100)
                    results["gpu_mem_mb"].append(gpus[0].memoryUsed)
            except Exception:
                pass
        prev_net = net
        prev_time = now


def sample_grabs():
    # Simulate the three grabs Decypher does each tick
    # Use approximate screen regions at 1920x1080 as stand-in
    import ctypes
    user32 = ctypes.windll.user32
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    bboxes = [
        # strip
        (int(sw * 0.8875), int(sh * 0.27), int(sw * 0.9225), int(sh * 0.56)),
        # menu button
        (int(sw * 0.43),   int(sh * 0.91), int(sw * 0.57),   int(sh * 0.958)),
        # clove ult
        (int(sw * 0.5707), int(sh * 0.966), int(sw * 0.6053), int(sh * 0.970)),
    ]
    while not stop_flag.is_set():
        t0 = time.perf_counter()
        if PIL_AVAILABLE:
            for bb in bboxes:
                try:
                    ImageGrab.grab(bbox=bb, all_screens=True)
                except Exception:
                    pass
        elapsed_ms = (time.perf_counter() - t0) * 1000
        results["grab_ms"].append(elapsed_ms)
        time.sleep(max(0, GRAB_INTERVAL - elapsed_ms / 1000))


def summarise(label, data, unit, fmt=".1f"):
    if not data:
        print(f"  {label:<22} no data")
        return
    print(f"  {label:<22} avg={statistics.mean(data):{fmt}}{unit}  "
          f"min={min(data):{fmt}}{unit}  max={max(data):{fmt}}{unit}  "
          f"p95={sorted(data)[int(len(data)*0.95)]:{fmt}}{unit}")


OUTPUT_FILE = "perf_monitor.txt"

import sys
class Tee:
    def __init__(self, f): self.f = f
    def write(self, x): sys.__stdout__.write(x); self.f.write(x)
    def flush(self): sys.__stdout__.flush(); self.f.flush()

_outfile = open(OUTPUT_FILE, "w", encoding="utf-8")
sys.stdout = Tee(_outfile)

print(f"Running for {DURATION_SECONDS}s — keep Valorant open and play normally...\n")

process.cpu_percent(interval=None)  # prime the counter

t_sys   = threading.Thread(target=sample_system, daemon=True)
t_grabs = threading.Thread(target=sample_grabs,  daemon=True)
t_sys.start()
t_grabs.start()

time.sleep(DURATION_SECONDS)
stop_flag.set()
t_sys.join(timeout=2)
t_grabs.join(timeout=2)

print("=" * 60)
print("RESULTS")
print("=" * 60)
print("\nProcess (this script proxies Decypher's grab pattern):")
summarise("CPU %",          results["cpu_pct"],     "%")
summarise("RAM",            results["ram_mb"],      " MB")
print("\nNetwork (whole machine delta):")
summarise("Sent",           results["net_sent_kb"], " KB/s")
summarise("Recv",           results["net_recv_kb"], " KB/s")
print("\nImageGrab (3 grabs per 250ms tick):")
summarise("Total grab time", results["grab_ms"],    " ms")
if results["grab_ms"]:
    overhead_pct = statistics.mean(results["grab_ms"]) / (GRAB_INTERVAL * 1000) * 100
    print(f"  {'Tick overhead':<22} {overhead_pct:.1f}% of each 250ms window")
if GPU_AVAILABLE and results["gpu_load_pct"]:
    print("\nGPU:")
    summarise("Load",        results["gpu_load_pct"], "%")
    summarise("VRAM used",   results["gpu_mem_mb"],   " MB")
elif not GPU_AVAILABLE:
    print("\nGPU: install GPUtil for GPU stats  (pip install gputil)")
print("=" * 60)
