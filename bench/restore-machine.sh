#!/usr/bin/env bash
# Put the machine back exactly as the benchmark found it: neighbour containers
# running again, CPU governor back on powersave.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

LIST="$ROOT/.run/paused-containers.txt"
if [[ -f "$LIST" ]]; then
  echo "restarting $(wc -l < "$LIST") containers"
  xargs -a "$LIST" docker start
else
  echo "no container list found — nothing to restart"
fi

if [[ "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)" != "powersave" ]]; then
  echo
  echo "CPU governor is still 'performance'. Restore it with:"
  echo "  for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do echo powersave | sudo tee \$g >/dev/null; done"
  echo "(run it yourself, or ask me and I'll open a terminal window for the prompt)"
fi
