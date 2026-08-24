"""Walk the demo journey against a running instance.

Exercises exactly what the audience clicks, in order, and fails loudly if any
step would leave them stuck. Point it at localhost during development or at the
deployed URL before presenting:

    uv run python -m scripts.smoke_journey http://localhost:8000
    uv run python -m scripts.smoke_journey https://agent-improver.onrender.com
"""
from __future__ import annotations

import sys

import httpx

SPA_ROUTES = [
    "/",
    "/agents/support-refund-agent",
    "/discovery",
    "/patterns/P6",
    "/patterns/P6/improve",
]


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    c = httpx.Client(base_url=base, timeout=600, follow_redirects=True)
    problems: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
        if not ok:
            problems.append(label)

    print(f"journey smoke against {base}\n")

    h = c.get("/api/health").json()
    check("health", h["ok"], " ".join(f"{k}={v}" for k, v in h["subsystems"].items()))
    check("all subsystems real", all(v == "real" for v in h["subsystems"].values()))

    print("\nstep 1-2 — agents and overview")
    a = c.get("/api/agent").json()
    check("corpus loaded", a["corpus"]["total_traces"] == 1000, f"{a['corpus']['total_traces']} traces")
    check("baseline config active", a["active_config"]["version"] == "v1",
          f"active={a['active_config']['version']} (promote resets on redeploy)")

    print("\nstep 3 — discovery")
    d = c.post("/api/discovery/run").json()
    check("patterns found", len(d["patterns"]) >= 3, f"{len(d['patterns'])} clusters, k={d['cluster_k']}")

    print("\nstep 4 — investigate every pattern")
    kinds: dict[str, str] = {}
    for p in d["patterns"]:
        pid = p["pattern_id"]
        r = c.post(f"/api/patterns/{pid}/diagnose").json()
        dg = r["diagnosis"]
        kinds[pid] = dg["remediation_kind"]
        check(
            f"{pid} diagnosed",
            r["provenance"]["verified"],
            f"{dg['verdict']}/{dg['remediation_kind']}",
        )

    print("\nstep 5 — improve")
    config_patterns = [pid for pid, k in kinds.items() if k == "config"]
    check("a config-remediable pattern exists", bool(config_patterns), ", ".join(config_patterns))

    for pid in config_patterns[:1]:
        patch = c.post(f"/api/patterns/{pid}/patch").json()
        versions = [x["candidate_version"] for x in patch["candidates"] if x["within_edit_boundary"]]
        check(f"{pid} patch", len(versions) == 2, ", ".join(versions))
        blocked = passed = False
        for v in versions:
            resp = c.post("/api/replay/run", params={"pattern_id": pid, "candidate_version": v, "size": 12})
            if resp.status_code != 200:
                check(f"replay {v}", False, f"HTTP {resp.status_code} {resp.text[:120]}")
                continue
            j = resp.json()
            g = j["gate"]
            check(f"replay {v}", True, f"gate={g['verdict']} promotable={g['promotable']}")
            check(f"{v} no external calls executed", j["candidate_metrics"]["external_calls_executed"] == 0)
            check(f"{v} source worlds intact", j["world_isolation"]["source_worlds_mutated"] == 0)
            blocked = blocked or not g["promotable"]
            passed = passed or g["promotable"]
        check("one candidate blocked, one promotable", blocked and passed,
              "the gate has to be seen doing both")

    for pid in [p for p, k in kinds.items() if k != "config"][:2]:
        r = c.post(f"/api/patterns/{pid}/propose").json()
        check(f"{pid} proposal", r["kind"] == kinds[pid], f"kind={r['kind']}")

    print("\nSPA routes")
    for route in SPA_ROUTES:
        code = c.get(route).status_code
        check(f"GET {route}", code == 200, str(code))

    print()
    if problems:
        print(f"FAILED — {len(problems)} problem(s): {', '.join(problems)}")
        return 1
    print("PASSED — the full demo journey is clickable end to end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
