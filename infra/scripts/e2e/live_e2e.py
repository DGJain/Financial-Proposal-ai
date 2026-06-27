#!/usr/bin/env python
"""Live end-to-end checks against a running backend over a REAL database.

Assumes the schema is migrated, demo data is seeded, and the API is serving at
BASE_URL. Exercises the Phase 5 read surface (and the readiness probe) through
HTTP so the whole persistence path — migrations, real PostgreSQL round-trips, the
ASGI app — is validated together, the integration the unit tests fake with SQLite.

Usage:
    BASE_URL=http://localhost:8000 python infra/scripts/e2e/live_e2e.py
"""

from __future__ import annotations

import os
import sys

import httpx

BASE = os.environ.get("BASE_URL", "http://localhost:8000")
_passed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global _passed
    if condition:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        raise SystemExit(1)


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=15.0) as c:
        # liveness + readiness
        health = c.get("/health").json()
        check("/health ok", health.get("status") == "ok", str(health))
        ready = c.get("/ready")
        check("/ready 200", ready.status_code == 200, ready.text)
        check("/ready database", ready.json()["checks"].get("database") is True, ready.text)

        # history → discover the seeded runs
        hist = c.get("/history", params={"limit": 100}).json()
        rows = hist["rows"]
        generated = [r for r in rows if r["outcome"] == "generated"]
        refused = [r for r in rows if r["outcome"] == "refused"]
        check("history has a generated run", len(generated) >= 1)
        check("history has a refused run", len(refused) >= 1)
        gen = generated[0]
        check("generated row has quality", gen["ocr_confidence"] is not None, str(gen))
        check("refused row has no quality", refused[0]["ocr_confidence"] is None)

        # execution report (real lineage join)
        report = c.get(f"/report/{gen['gen_id']}").json()
        check("report prompt present", bool(report["prompt"]))
        check("report retrieved financial", len(report["retrieved_financial"]) >= 1)
        check("report quality joined", report["quality"] is not None, str(report["quality"]))
        check("report has 5 stages", len(report["stages"]) == 5)
        check("report has citations", len(report["citations"]) >= 1)

        # refused report still resolves
        ref_report = c.get(f"/report/{refused[0]['gen_id']}").json()
        check("refused report quality null", ref_report["quality"] is None)
        check("refused report no stages", ref_report["stages"] == [])

        # repository metrics
        repo = c.get("/metrics/repository").json()
        check("repo financial docs >= 1", repo["financial_documents"] >= 1, str(repo))
        check("repo embedded chunks > 0", repo["embedded_chunks"] > 0, str(repo))
        check("repo last ingestion set", repo["last_ingestion_ts"] is not None)

        # generation health
        health_m = c.get("/metrics/generation-health", params={"days": 7}).json()
        check("gen-health runs_total >= 2", health_m["runs_total"] >= 2, str(health_m))
        check("gen-health 7 daily bars", len(health_m["daily"]) == 7)

        # export + lifecycle
        pid = gen["proposal_id"]
        exp = c.get(f"/proposals/{pid}/export", params={"format": "markdown"})
        check("export 200 markdown", exp.status_code == 200, exp.text[:200])
        check("export has heading", "Engagement Overview" in exp.text)
        check("export has lineage", "Lineage & Provenance" in exp.text)
        after = c.get(f"/proposals/{pid}").json()
        check("proposal marked exported", after["status"] == "exported", str(after))

    print(f"\nLive E2E passed — {_passed} checks against {BASE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
