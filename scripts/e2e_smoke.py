#!/usr/bin/env python3
"""End-to-end smoke tests for iDoctor Design (fixture + optional live + API).

Usage:
  PYTHONPATH=. python scripts/e2e_smoke.py
  PYTHONPATH=. python scripts/e2e_smoke.py --live
  PYTHONPATH=. python scripts/e2e_smoke.py --api
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _ok(msg: str) -> None:
    print(f"  OK  {msg}")


def _fail(msg: str) -> None:
    print(f"FAIL  {msg}")
    raise SystemExit(1)


def test_fixture() -> str:
    print("=== E2E: fixture pipeline ===")
    from backend.contracts.validate import (
        validate_designs,
        validate_eval,
        validate_provenance,
        validate_smallmol,
        validate_spec,
        validate_verdicts,
    )
    from backend.pipeline import run_idoctor_design

    r = run_idoctor_design("fixture")
    validate_provenance(r["provenance"])
    validate_spec(r["scientific_spec"])
    validate_designs(r["designs"])
    validate_smallmol(r["smallmol"])
    validate_eval(r["eval_result"])
    validate_verdicts(r["verdicts"])

    items = r["verdicts"].get("items") or r["verdicts"].get("verdicts") or []
    promotes = [v for v in items if v.get("verdict", v.get("decision")) == "promote"]
    rejects = [v for v in items if v.get("verdict", v.get("decision")) == "reject"]
    if not promotes:
        _fail("expected at least one promote")
    if not rejects:
        _fail("expected at least one reject")
    if not r.get("experiment_md"):
        _fail("expected experiment.md")

    _ok(f"run_id={r['run_id']}")
    _ok(f"nodes={r['provenance'].get('nodes')}")
    _ok(f"promote={len(promotes)} reject={len(rejects)}")
    _ok(f"experiment={len(r['experiment_md'])} chars")
    return r["run_id"]


def test_live() -> str:
    print("=== E2E: live pipeline (partner keys optional) ===")
    from backend.config import ANTHROPIC_API_KEY, PAPERCLIP_API_KEY, TAMARIND_API_KEY
    from backend.pipeline import run_idoctor_design

    print(
        "  keys:",
        f"anthropic={'yes' if ANTHROPIC_API_KEY else 'no'}",
        f"paperclip={'yes' if PAPERCLIP_API_KEY else 'no'}",
        f"tamarind={'yes' if TAMARIND_API_KEY else 'no'}",
    )
    r = run_idoctor_design("live")
    nodes = r["provenance"].get("nodes") or {}
    designs = (r.get("designs") or {}).get("designs") or []
    if not designs:
        _fail("live run produced no designs")
    items = (r.get("verdicts") or {}).get("items") or (r.get("verdicts") or {}).get("verdicts") or []
    promotes = [v for v in items if v.get("verdict", v.get("decision")) == "promote"]
    rejects = [v for v in items if v.get("verdict", v.get("decision")) == "reject"]
    if not promotes or not rejects:
        _fail(f"expected promote+reject, got promote={len(promotes)} reject={len(rejects)}")
    if not r.get("experiment_md"):
        _fail("expected experiment.md")

    fixture_designs = REPO / "frontend" / "public" / "fixtures" / "designs.example.json"
    fixture_seqs = set()
    if fixture_designs.is_file():
        fixture_doc = json.loads(fixture_designs.read_text())
        fixture_seqs = {
            d.get("sequence")
            for d in (fixture_doc.get("designs") or [])
            if d.get("sequence")
        }
    collision = any(d.get("sequence") in fixture_seqs for d in designs[:3])
    _ok(f"run_id={r['run_id']}")
    _ok(f"nodes={nodes}")
    _ok(f"first design provenance={designs[0].get('provenance')}")
    _ok(f"fixture_seq_collision={collision}")
    return r["run_id"]


def test_api(base: str = "http://127.0.0.1:8080") -> None:
    print(f"=== E2E: HTTP API @ {base} ===")

    def get(path: str):
        with urllib.request.urlopen(f"{base}{path}", timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())

    def post(path: str, body: dict):
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{base}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())

    try:
        status, health = get("/api/health")
    except urllib.error.URLError as exc:
        _fail(f"API not reachable ({exc}). Start: PYTHONPATH=. .venv/bin/python -m uvicorn backend.main:app --port 8080")

    _ok(f"GET /api/health → {status} {health}")
    status, latest = get("/api/runs/latest")
    _ok(f"GET /api/runs/latest → {status} run_id={latest.get('run_id')}")

    status, job = post("/api/run", {"mode": "fixture"})
    job_id = job.get("job_id")
    if not job_id:
        _fail(f"POST /api/run missing job_id: {job}")
    _ok(f"POST /api/run → job_id={job_id}")

    deadline = time.time() + 180
    last: dict | None = None
    while time.time() < deadline:
        try:
            _, last = get(f"/api/results/{job_id}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()
            last = {"status": "error", "http": exc.code, "body": body[:300]}
            break
        st = (last or {}).get("status")
        if st in {"completed", "failed", "error"}:
            break
        time.sleep(1.0)

    if not last or last.get("status") != "completed":
        _fail(f"job did not complete: {last}")
    items = (last.get("verdicts") or {}).get("items") or []
    promotes = [v for v in items if v.get("verdict") == "promote"]
    rejects = [v for v in items if v.get("verdict") == "reject"]
    if not promotes or not rejects:
        _fail(f"API results missing promote/reject: {len(promotes)}/{len(rejects)}")
    _ok(f"results run_id={last.get('run_id')} promote={len(promotes)} reject={len(rejects)}")
    print("  API E2E OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="also run live pipeline")
    parser.add_argument("--api", action="store_true", help="also hit FastAPI on :8080")
    parser.add_argument("--api-base", default="http://127.0.0.1:8080")
    args = parser.parse_args()

    test_fixture()
    if args.live:
        test_live()
    if args.api:
        test_api(args.api_base)
    print("\nALL E2E CHECKS PASSED")


if __name__ == "__main__":
    main()
