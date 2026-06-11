import json, platform, psutil, time, socket, subprocess
from pathlib import Path

def net_io():
    n = psutil.net_io_counters()
    time.sleep(0.5)
    n2 = psutil.net_io_counters()
    bps = ((n2.bytes_sent + n2.bytes_recv) - (n.bytes_sent + n.bytes_recv)) * 2
    return round(bps / 1_000_000, 2)

def disks():
    out = []
    for p in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(p.mountpoint)
            out.append({"mount": p.mountpoint, "total_gb": round(u.total/1e9,1),
                        "used_gb": round(u.used/1e9,1), "pct": u.percent})
        except Exception:
            pass
    return out

def gpu_info():
    try:
        r = subprocess.run(
            ["nvidia-smi","--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        gpus = []
        for line in r.stdout.strip().splitlines():
            parts = [x.strip() for x in line.split(",")]
            if len(parts) >= 5:
                gpus.append({"name": parts[0], "util_pct": int(parts[1]),
                             "mem_used_mb": int(parts[2]), "mem_total_mb": int(parts[3]),
                             "temp_c": int(parts[4])})
        return gpus
    except Exception:
        return []

data = {
    "timestamp": time.time(), "hostname": socket.gethostname(),
    "platform": platform.platform(),
    "cpu": {"count_logical": psutil.cpu_count(),
             "count_physical": psutil.cpu_count(logical=False),
             "freq_mhz": round(psutil.cpu_freq().current,1) if psutil.cpu_freq() else 0,
             "usage_pct": psutil.cpu_percent(interval=1),
             "per_core": psutil.cpu_percent(interval=0.2, percpu=True)},
    "memory": {"total_gb": round(psutil.virtual_memory().total/1e9,1),
               "used_gb": round(psutil.virtual_memory().used/1e9,1),
               "pct": psutil.virtual_memory().percent},
    "swap": {"total_gb": round(psutil.swap_memory().total/1e9,1),
              "used_gb": round(psutil.swap_memory().used/1e9,1),
              "pct": psutil.swap_memory().percent},
    "net_mbps": net_io(),
    "disks": disks(),
    "gpu": gpu_info(),
    "processes": sorted(
        [{"pid": p.pid, "name": p.name(), "cpu": p.cpu_percent(),
          "mem_mb": round(p.memory_info().rss/1e6,1)}
         for p in psutil.process_iter(["pid","name","cpu_percent","memory_info"])
         if p.info["memory_info"]],
        key=lambda x: x["mem_mb"], reverse=True)[:20],
}
out = Path(__file__).parent / "syscity_data.json"
out.write_text(json.dumps(data, indent=2))
print(f"[syscity_snapshot] Saved to {out}")
print(f"  CPU {data['cpu']['usage_pct']}%  RAM {data['memory']['pct']}%  NET {data['net_mbps']} Mbps  GPUs {len(data['gpu'])}")
