"""How often can she actually not reach the model?

The model runs locally (Ollama) now, so there's no hosted-API outage to
report on -- but Ollama can still be not running, or the model not pulled,
or a stream can still drop mid-reply. What CLOUD_FALLBACK_LOG records are
those failures. This script reads what it has recorded, so the choice of
model and its settings can be revisited from a week of real use instead of a
guess.

    python fallback_report.py            # last 7 days
    python fallback_report.py --days 30  # a longer window
"""

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timedelta

from config import DATA_DIR

FALLBACK_LOG = DATA_DIR / "cloud_fallback_log.jsonl"
LIA_LOG = DATA_DIR / "lia.log"

_SUCCESS_LINE = re.compile(r"\[cloud: \d+ in / \d+ out\]")


def _read_fallbacks(since: datetime) -> list[dict]:
    if not FALLBACK_LOG.exists():
        return []
    rows = []
    for line in FALLBACK_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        try:
            at = datetime.fromisoformat(row.get("at", ""))
        except ValueError:
            continue
        if at >= since:
            rows.append(row)
    return rows


def _count_successes() -> int:
    # lia.log lines aren't timestamped (TeeLog is a plain passthrough -- see
    # app.py), so this is an all-time total, not windowed to --days. Said
    # plainly below rather than implying a precision this doesn't have.
    if not LIA_LOG.exists():
        return 0
    return sum(1 for line in LIA_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
               if _SUCCESS_LINE.search(line))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    since = datetime.now() - timedelta(days=args.days)
    fallbacks = _read_fallbacks(since)
    successes = _count_successes()

    print(f"Cloud fallback report -- last {args.days} day(s)\n")

    if not fallbacks:
        print(f"No fallbacks logged. ({successes} successful cloud completions all-time"
              " in lia.log, unwindowed -- see note below.)")
        return

    reasons = Counter(row.get("reason", "unknown") for row in fallbacks)
    mid_stream = sum(1 for row in fallbacks if row.get("mid_stream"))

    print(f"{len(fallbacks)} fallback(s) in the last {args.days} day(s)"
          f" ({mid_stream} of them mid-reply, the rest before she started speaking):")
    for reason, count in reasons.most_common():
        print(f"  {count:>3}  {reason}")

    print(f"\n{successes} successful cloud completions all-time in lia.log.")
    print("That total isn't windowed to --days -- lia.log lines carry no "
          "timestamp, only cloud_fallback_log.jsonl does. Treat the ratio as "
          "directional, not exact, until that's added too.")


if __name__ == "__main__":
    main()
