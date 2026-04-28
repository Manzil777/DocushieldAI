#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORTS_DIR="$ROOT_DIR/reports"
REPORT_PATH="$REPORTS_DIR/bandit_report.json"

mkdir -p "$REPORTS_DIR"

if ! command -v bandit >/dev/null 2>&1; then
  echo "bandit is not installed in the active environment" >&2
  exit 127
fi

bandit_exit=0
bandit -r "$ROOT_DIR/backend/" -f json -o "$REPORT_PATH" || bandit_exit=$?

python - "$REPORT_PATH" <<'PY'
import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
if not report_path.exists():
    print("bandit report was not generated", file=sys.stderr)
    sys.exit(1)

payload = json.loads(report_path.read_text(encoding="utf-8"))
results = payload.get("results", [])
severity_totals = {"HIGH": 0, "MEDIUM": 0}

for result in results:
    severity = str(result.get("issue_severity", "")).upper()
    if severity in severity_totals:
        severity_totals[severity] += 1

print(
    json.dumps(
        {
            "report": str(report_path),
            "total_results": len(results),
            "high_issues": severity_totals["HIGH"],
            "medium_issues": severity_totals["MEDIUM"],
        },
        indent=2,
    )
)
PY

if [ "$bandit_exit" -gt 1 ]; then
  exit "$bandit_exit"
fi
