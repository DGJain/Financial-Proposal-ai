#!/usr/bin/env python
"""Offline structural lint for the rendered Kubernetes manifests.

A cluster-free sanity check that complements ``kubectl kustomize`` (which already
proves the YAML parses): it verifies every resource has the required identity
fields, that Deployment/StatefulSet/Job selectors are satisfied by their pod
template labels, that Services select something, and that every workload container
is hardened (non-root, no privilege escalation, dropped caps, resource limits).

Usage:
    kubectl kustomize infra/k8s | python infra/scripts/validate_manifests.py -
    python infra/scripts/validate_manifests.py rendered.yaml
"""

from __future__ import annotations

import sys

import yaml

WORKLOADS = {"Deployment", "StatefulSet", "Job"}


def _load(source: str) -> list[dict]:
    text = sys.stdin.read() if source == "-" else open(source, encoding="utf-8").read()
    return [d for d in yaml.safe_load_all(text) if d]


def _pod_spec(doc: dict) -> dict | None:
    return doc.get("spec", {}).get("template", {}).get("spec")


def validate(docs: list[dict]) -> list[str]:
    errors: list[str] = []

    def err(name: str, msg: str) -> None:
        errors.append(f"[{name}] {msg}")

    for doc in docs:
        kind = doc.get("kind", "<no kind>")
        name = doc.get("metadata", {}).get("name", "<no name>")
        ref = f"{kind}/{name}"

        if not doc.get("apiVersion"):
            err(ref, "missing apiVersion")
        if not doc.get("metadata", {}).get("name"):
            err(ref, "missing metadata.name")

        if kind in WORKLOADS:
            pod = _pod_spec(doc)
            if pod is None:
                err(ref, "missing spec.template.spec")
                continue
            tmpl_labels = doc["spec"]["template"].get("metadata", {}).get("labels", {})
            selector = doc["spec"].get("selector", {}).get("matchLabels", {})
            # Deployment/StatefulSet require a selector matched by the template.
            if kind != "Job":
                if not selector:
                    err(ref, "missing spec.selector.matchLabels")
                for k, v in selector.items():
                    if tmpl_labels.get(k) != v:
                        err(ref, f"selector {k}={v} not matched by pod template labels")
            containers = pod.get("containers", [])
            if not containers:
                err(ref, "no containers")
            pod_sc = pod.get("securityContext", {})
            for c in containers:
                cname = c.get("name", "<no name>")
                if not c.get("image"):
                    err(ref, f"container {cname} missing image")
                sc = c.get("securityContext", {})
                if sc.get("allowPrivilegeEscalation") is not False:
                    err(ref, f"container {cname} allowPrivilegeEscalation must be false")
                if "ALL" not in sc.get("capabilities", {}).get("drop", []):
                    err(ref, f"container {cname} must drop ALL capabilities")
                if not (sc.get("runAsNonRoot") or pod_sc.get("runAsNonRoot")):
                    err(ref, f"container {cname} must run as non-root")
                limits = c.get("resources", {}).get("limits", {})
                if not ("cpu" in limits and "memory" in limits):
                    err(ref, f"container {cname} missing cpu/memory limits")

        if kind == "Service":
            if not doc.get("spec", {}).get("selector"):
                err(ref, "Service has no selector")

    return errors


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else "-"
    docs = _load(source)
    errors = validate(docs)
    print(f"validated {len(docs)} resources")
    if errors:
        print(f"\n{len(errors)} problem(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("OK — all resources structurally valid and hardened")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
