from __future__ import annotations

import argparse
import json
import math
import mimetypes
import random
import sys
import time
from pathlib import Path
from uuid import uuid4

import requests


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_FILE_PATH = ROOT_DIR / "backend" / "tests" / "fixtures" / "aadhaar_sample.jpg"
RESULTS_PATH = ROOT_DIR / "data" / "benchmark_results.json"
REPORT_PATH = ROOT_DIR / "docs" / "performance_report.md"
DEFAULT_MASK_FIELDS = ["uid", "dob"]
MASK_FIELD_ALIASES = {
    "uid": "uid",
    "aadhaar_number": "uid",
    "dob": "dob",
    "name": "name",
    "address": "address",
    "gender": "gender",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an end-to-end latency benchmark against the DocuShield API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL for the FastAPI server.")
    parser.add_argument(
        "--file",
        dest="file_path",
        default=str(DEFAULT_FILE_PATH),
        help="Path to the input document used for each iteration.",
    )
    parser.add_argument("--iterations", type=int, default=50, help="Number of benchmark iterations to run.")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.5,
        help="Seconds to wait between status polls when the status endpoint is available.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-iteration timeout in seconds while waiting for processing to complete.",
    )
    parser.add_argument(
        "--simulate-network-delay",
        action="store_true",
        help="Add a random 0.1s to 0.3s delay before each request to approximate local network variability.",
    )
    parser.add_argument(
        "--mask-fields",
        nargs="*",
        default=None,
        help="Optional explicit mask fields. Defaults to detected fields, then uid/dob as a fallback.",
    )
    return parser.parse_args()


def maybe_add_delay(enabled: bool) -> None:
    if enabled:
        time.sleep(random.uniform(0.1, 0.3))


def request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    expected_statuses: tuple[int, ...] = (200,),
    **kwargs,
) -> dict:
    response = session.request(method=method, url=url, timeout=60, **kwargs)
    if response.status_code not in expected_statuses:
        raise RuntimeError(f"{method} {url} failed with {response.status_code}: {response.text}")
    return response.json()


def register_and_login(session: requests.Session, base_url: str) -> dict[str, str]:
    email = f"benchmark-{uuid4().hex}@example.com"
    password = "benchmark-pass-123"
    request_json(
        session,
        "POST",
        f"{base_url}/auth/register",
        json={"email": email, "password": password},
    )
    login_payload = request_json(
        session,
        "POST",
        f"{base_url}/auth/login",
        json={"email": email, "password": password},
    )
    return {"Authorization": f"Bearer {login_payload['access_token']}"}


def infer_content_type(file_path: Path) -> str:
    guessed_type, _ = mimetypes.guess_type(file_path.name)
    return guessed_type or "application/octet-stream"


def upload_document(
    session: requests.Session,
    base_url: str,
    file_path: Path,
    headers: dict[str, str],
    simulate_network_delay: bool,
) -> dict:
    maybe_add_delay(simulate_network_delay)
    with file_path.open("rb") as file_obj:
        return request_json(
            session,
            "POST",
            f"{base_url}/documents/upload",
            headers=headers,
            files={"file": (file_path.name, file_obj, infer_content_type(file_path))},
        )


def poll_status(
    session: requests.Session,
    base_url: str,
    document_id: str,
    headers: dict[str, str],
    timeout_seconds: float,
    poll_interval_seconds: float,
    simulate_network_delay: bool,
) -> dict | None:
    deadline = time.time() + timeout_seconds
    status_url = f"{base_url}/documents/{document_id}/status"
    last_payload: dict | None = None

    while time.time() <= deadline:
        maybe_add_delay(simulate_network_delay)
        response = session.get(status_url, headers=headers, timeout=60)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise RuntimeError(f"GET {status_url} failed with {response.status_code}: {response.text}")

        payload = response.json()
        last_payload = payload
        status_value = payload.get("status")
        if status_value == "completed":
            return payload
        if status_value == "failed":
            raise RuntimeError(f"Document {document_id} processing failed: {payload}")

        time.sleep(poll_interval_seconds)

    raise TimeoutError(f"Timed out waiting for document {document_id} to complete: {last_payload}")


def normalize_mask_field(field_name: str) -> str | None:
    return MASK_FIELD_ALIASES.get(field_name.strip().lower())


def determine_mask_fields(
    upload_payload: dict,
    status_payload: dict | None,
    explicit_mask_fields: list[str] | None,
) -> list[str]:
    if explicit_mask_fields:
        return explicit_mask_fields

    selected_fields: list[str] = []
    candidate_sources = [
        (status_payload or {}).get("fields", {}),
        upload_payload.get("fields", {}),
        (status_payload or {}).get("detections", {}),
    ]

    for source in candidate_sources:
        if not isinstance(source, dict):
            continue
        for field_name in source.keys():
            normalized = normalize_mask_field(field_name)
            if normalized and normalized not in selected_fields:
                selected_fields.append(normalized)

    return selected_fields or DEFAULT_MASK_FIELDS


def mask_document(
    session: requests.Session,
    base_url: str,
    document_id: str,
    headers: dict[str, str],
    mask_fields: list[str],
    simulate_network_delay: bool,
) -> dict:
    maybe_add_delay(simulate_network_delay)
    return request_json(
        session,
        "POST",
        f"{base_url}/documents/{document_id}/mask",
        headers=headers,
        json={"mask_fields": mask_fields},
    )


def percentile(values: list[float], percentile_value: int) -> float:
    if not values:
        raise ValueError("Cannot compute percentiles from an empty list")

    sorted_values = sorted(values)
    rank = max(1, math.ceil((percentile_value / 100) * len(sorted_values)))
    return sorted_values[rank - 1]


def write_results(latencies: list[float]) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = [{"latency": round(latency, 4)} for latency in latencies]
    RESULTS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_report(
    *,
    iterations: int,
    average_latency: float,
    p50: float,
    p95: float,
    p99: float,
    file_path: Path,
    simulate_network_delay: bool,
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        display_file_path = file_path.relative_to(ROOT_DIR)
    except ValueError:
        display_file_path = file_path
    network_note = (
        "A random 0.1s to 0.3s delay was added before each request to approximate local network variability."
        if simulate_network_delay
        else "Runs were measured locally against the configured API with no artificial network delay."
    )
    report = f"""# Performance Report

## Methodology

- Benchmark script: `python scripts/benchmark.py`
- Benchmark setup: register/login once, then upload document, poll `/documents/{{id}}/status` until completed when available, then call `/documents/{{id}}/mask` for each iteration
- Iterations: {iterations}
- Input file: `{display_file_path}`
- Network conditions: {network_note}
- Stage timings are emitted by backend logs using `time.time()` for OCR, PII detection, masking, and total processing time

## Results

- Average latency: {average_latency:.3f}s
- p50: {p50:.3f}s
- p95: {p95:.3f}s
- p99: {p99:.3f}s

## Observations

- This benchmark measures end-to-end API latency through the live HTTP interface.
- Stage-level timing data is available in backend logs during the same run.
- OCR is expected to be the slowest stage in most runs because it performs the heaviest per-field extraction work after detection.
"""
    REPORT_PATH.write_text(report, encoding="utf-8")


def run_iteration(
    session: requests.Session,
    base_url: str,
    file_path: Path,
    headers: dict[str, str],
    timeout_seconds: float,
    poll_interval_seconds: float,
    simulate_network_delay: bool,
    explicit_mask_fields: list[str] | None,
) -> float:
    started_at = time.time()
    upload_payload = upload_document(session, base_url, file_path, headers, simulate_network_delay)
    document_id = upload_payload["document_id"]
    status_payload = poll_status(
        session,
        base_url,
        document_id,
        headers,
        timeout_seconds,
        poll_interval_seconds,
        simulate_network_delay,
    )
    mask_fields = determine_mask_fields(upload_payload, status_payload, explicit_mask_fields)
    mask_document(session, base_url, document_id, headers, mask_fields, simulate_network_delay)
    return time.time() - started_at


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    file_path = Path(args.file_path).expanduser().resolve()

    if args.iterations <= 0:
        raise ValueError("--iterations must be greater than 0")
    if not file_path.exists():
        raise FileNotFoundError(f"Benchmark file does not exist: {file_path}")

    session = requests.Session()
    headers = register_and_login(session, base_url)
    latencies: list[float] = []

    for iteration in range(1, args.iterations + 1):
        latency = run_iteration(
            session,
            base_url,
            file_path,
            headers,
            args.timeout,
            args.poll_interval,
            args.simulate_network_delay,
            args.mask_fields,
        )
        latencies.append(latency)
        print(f"iteration {iteration}: {latency:.3f}s")

    average_latency = sum(latencies) / len(latencies)
    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    p99 = percentile(latencies, 99)

    write_results(latencies)
    write_report(
        iterations=len(latencies),
        average_latency=average_latency,
        p50=p50,
        p95=p95,
        p99=p99,
        file_path=file_path,
        simulate_network_delay=args.simulate_network_delay,
    )

    print(f"p50: {p50:.3f}s")
    print(f"p95: {p95:.3f}s")
    print(f"p99: {p99:.3f}s")
    print(f"average: {average_latency:.3f}s")
    print(f"results written to: {RESULTS_PATH}")
    print(f"report written to: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"benchmark failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
