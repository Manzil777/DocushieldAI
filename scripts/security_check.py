from __future__ import annotations

import json
import os
import re
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SUSPICIOUS_DEFAULTS = {
    "change-me",
    "minioadmin",
}
REQUIRED_ENV_VARS = [
    "SECRET_KEY",
    "JWT_SECRET",
    "DATABASE_URL",
    "REDIS_URL",
    "MINIO_ENDPOINT",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
]
SCAN_PATHS = [
    ROOT_DIR / "backend" / "app" / "core" / "config.py",
    ROOT_DIR / "backend" / ".env",
    ROOT_DIR / ".env",
    ROOT_DIR / "docker-compose.yml",
    ROOT_DIR / "docker-compose.yaml",
]
SECRET_PATTERN = re.compile(
    r"(?i)(secret|password|api[_-]?key|access[_-]?key)[^\\n=:\\\"]*[:=][^\\n]*['\\\"]?([^'\\\"\\s]+)['\\\"]?"
)


def find_hardcoded_secret_candidates() -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []

    for path in SCAN_PATHS:
        if not path.is_file():
            continue

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        for line_number, line in enumerate(lines, start=1):
            lower_line = line.lower()
            if any(default_value in lower_line for default_value in SUSPICIOUS_DEFAULTS):
                candidates.append(
                    {
                        "path": str(path.relative_to(ROOT_DIR)),
                        "line": line_number,
                        "reason": "suspicious default value",
                        "snippet": line.strip(),
                    }
                )
                continue

            match = SECRET_PATTERN.search(line)
            if not match:
                continue

            value = match.group(2).strip()
            if value and len(value) >= 8 and not value.startswith("${"):
                candidates.append(
                    {
                        "path": str(path.relative_to(ROOT_DIR)),
                        "line": line_number,
                        "reason": "hardcoded secret-like assignment",
                        "snippet": line.strip(),
                    }
                )

    return candidates


def main() -> int:
    env_summary = {
        name: {
            "present": bool(os.getenv(name)),
            "value_source": "environment" if os.getenv(name) else "missing",
        }
        for name in REQUIRED_ENV_VARS
    }
    missing_env = [name for name, status in env_summary.items() if not status["present"]]
    secret_candidates = find_hardcoded_secret_candidates()

    payload = {
        "required_env_vars": env_summary,
        "missing_env_vars": missing_env,
        "hardcoded_secret_candidates": secret_candidates,
    }
    print(json.dumps(payload, indent=2))
    return 1 if missing_env or secret_candidates else 0


if __name__ == "__main__":
    raise SystemExit(main())
