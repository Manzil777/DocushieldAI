# Performance Report

## Methodology

- Benchmark script: `python scripts/benchmark.py`
- Mode: `local`
- Benchmark setup: register/login once, then run upload, processing, persistence, and masking in-process against the backend services without opening a local port
- Iterations: 5
- Input file: `backend/tests/fixtures/aadhaar_sample.jpg`
- Network conditions: No network transport was used; measurements exclude HTTP socket overhead.
- Stage timings are emitted by backend logs using `time.time()` for OCR, PII detection, masking, and total processing time

## Results

- Average latency: 0.664s
- p50: 0.621s
- p95: 0.846s
- p99: 0.846s

## Observations

- This benchmark measures the end-to-end backend processing flow in-process without HTTP socket overhead.
- Stage-level timing data is available in backend logs during the same run.
- OCR is expected to be the slowest stage in most runs because it performs the heaviest per-field extraction work after detection.
