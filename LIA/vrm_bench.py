"""What the avatar actually costs, measured, not guessed.

Samples the running Lia process tree -- the pythonw.exe conversation loop plus
every child it spawns (WebView2's msedgewebview2.exe renderer/browser/gpu
processes, which is where most of the RAM lives) -- and reports working set,
CPU and GPU utilisation. `lia.log` shows what she says; this shows what she
costs.

    python LIA\\vrm_bench.py                 # 30 seconds, sampling every 5
    python LIA\\vrm_bench.py --seconds 60
    python LIA\\vrm_bench.py --label after   # tag a run, for side-by-side

Sampling is done through PowerShell (Get-Process, and the "GPU Engine"
performance counters) so there is no dependency to install -- which also means
this is Windows-only, like everything else in the app. Ctrl+C stops early and
prints what it has.

Interpretation notes:
  * CPU is reported as a percentage of ALL cores, so it matches Task Manager's
    headline number rather than "percent of one core".
  * A machine with no GPU renders WebGL on the CPU, and the cost lands in the
    WebView2 processes, not the Python one; that split is why each process is
    listed rather than just the total.
  * GPU is the sum of the GPU Engine counters for those processes, so it can
    read slightly above 100 when several engines (3D, Copy, VideoDecode) are
    each busy.
"""

import argparse
import json
import statistics
import subprocess
import time
from pathlib import Path

# One PowerShell round trip per sample: find the app, walk its children, and
# read RAM + CPU for the whole tree plus the GPU counters for the same PIDs.
_SAMPLE_PS = r"""
$ErrorActionPreference = 'SilentlyContinue'
$procs = Get-CimInstance Win32_Process
$roots = @($procs | Where-Object {
    $_.Name -in @('pythonw.exe', 'python.exe') -and $_.CommandLine -like '*app.py*'
} | ForEach-Object { [int]$_.ProcessId })

$tree = New-Object System.Collections.ArrayList
foreach ($r in $roots) { [void]$tree.Add($r) }
$changed = $true
while ($changed) {
    $changed = $false
    foreach ($p in $procs) {
        $pp = [int]$p.ParentProcessId
        $cp = [int]$p.ProcessId
        if ($tree.Contains($pp) -and -not $tree.Contains($cp)) {
            [void]$tree.Add($cp)
            $changed = $true
        }
    }
}

$rows = foreach ($procId in $tree) {
    $pr = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($pr) {
        [pscustomobject]@{
            pid  = $procId
            name = $pr.ProcessName
            ws   = [int64]$pr.WorkingSet64
            cpu  = [double]$pr.CPU
        }
    }
}

$gpu = -1.0
if ($rows) {
    $pattern = 'pid_(' + ($tree -join '|') + ')_'
    $counters = (Get-Counter '\GPU Engine(*)\Utilization Percentage' -ErrorAction SilentlyContinue).CounterSamples
    $sum = ($counters | Where-Object { $_.InstanceName -match $pattern } |
            Measure-Object -Property CookedValue -Sum).Sum
    if ($null -ne $sum) { $gpu = [double]$sum } else { $gpu = 0.0 }
}

[pscustomobject]@{ rows = @($rows); gpu = $gpu } | ConvertTo-Json -Depth 4 -Compress
"""


def _sample() -> tuple[list[dict], float]:
    """(per-process rows, summed GPU percent) for one instant."""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _SAMPLE_PS],
        capture_output=True, text=True, timeout=90,
    ).stdout.strip()
    if not out:
        return [], -1.0
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return [], -1.0
    rows = data.get("rows") or []
    if isinstance(rows, dict):
        rows = [rows]
    return rows, float(data.get("gpu", -1.0))


def _pretty(mb: float) -> str:
    return f"{mb:,.0f} MB"


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure what the avatar costs.")
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    cores = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "[Environment]::ProcessorCount"],
        capture_output=True, text=True, timeout=30,
    ).stdout.strip() or "?"

    print(f"sampling for {args.seconds:.0f}s every {args.interval:.0f}s "
          f"({cores} cores){' -- ' + args.label if args.label else ''}")

    rams: list[float] = []          # total tree working set, MB
    cpus: list[float] = []          # machine-wide CPU %, between samples
    gpus: list[float] = []
    samples = 0
    first = None
    deadline = time.time() + args.seconds
    try:
        while time.time() < deadline or samples < 2:
            rows, gpu = _sample()
            if not rows:
                print("  no Lia process found -- is she running? "
                      "(pythonw LIA\\app.py)")
                return 1
            now = time.time()
            total_mb = sum(r["ws"] for r in rows) / 1024 / 1024
            cpu_s = sum(r["cpu"] for r in rows)
            rams.append(total_mb)
            if gpu >= 0:
                gpus.append(gpu)
            if first is not None and cores.isdigit():
                dt = now - first[0]
                if dt > 0:
                    cpus.append((cpu_s - first[1]) / dt / int(cores) * 100)
            first = (now, cpu_s)
            samples += 1

            # live line, so a hang or a runaway is visible as it happens
            print(f"  t={samples * args.interval:>3.0f}s  ram={_pretty(total_mb):>10}"
                  f"  cpu={(cpus[-1] if cpus else 0.0):>5.1f}%"
                  f"  gpu={(gpu if gpu >= 0 else 0.0):>5.1f}%  "
                  f"({len(rows)} procs)")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("  stopped early")

    if not rams:
        return 1

    # Name the big contributors: for each process name, its peak working set.
    peaks: dict[str, float] = {}
    rows, _ = _sample()
    for r in rows:
        peaks[r["name"]] = peaks.get(r["name"], 0.0) + r["ws"] / 1024 / 1024

    print()
    print(f"--- {' '.join(filter(None, ['Lia', args.label]))} "
          f"({samples} samples) ---")
    print(f"RAM  working set   min {_pretty(min(rams))}"
          f"   avg {_pretty(statistics.fmean(rams))}"
          f"   max {_pretty(max(rams))}")
    if len(rams) >= 2:
        drift = rams[-1] - rams[0]
        print(f"     drift over run {drift:+,.0f} MB "
              f"({'growing -- suspect a leak' if drift > 25 else 'flat'})")
    if cpus:
        print(f"CPU  all {cores} cores avg {statistics.fmean(cpus):.1f}%"
              f"   peak {max(cpus):.1f}%")
    if gpus:
        print(f"GPU  avg {statistics.fmean(gpus):.1f}%   peak {max(gpus):.1f}%")
    else:
        print("GPU  counters unavailable on this machine")
    if peaks:
        print("by process (current):")
        for name, mb in sorted(peaks.items(), key=lambda kv: -kv[1]):
            print(f"    {name:<22} {_pretty(mb):>10}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
