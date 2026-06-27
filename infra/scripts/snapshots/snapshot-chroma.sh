#!/usr/bin/env sh
# Snapshot / restore the ChromaDB persistent volume. Each of the three collections
# (repo_financial / repo_proposals / repo_templates) shares one persist directory
# but is logically independent; a filesystem-consistent copy captures all three at
# a point in time. Templates/curated proposals change slowly, the financial corpus
# faster — schedule accordingly (ARCHITECTURE_SUMMARY: independent snapshots).
#
# In-cluster usage (copies the StatefulSet's persist dir to a backup PVC mount):
#   POD=chromadb-0
#   kubectl -n fpp-data exec "$POD" -- tar czf - -C /chroma chroma > chroma-$(date +%F).tgz
#   # restore:
#   kubectl -n fpp-data exec -i "$POD" -- tar xzf - -C /chroma < chroma-YYYY-MM-DD.tgz
#
# This wrapper performs the snapshot half for a given pod.
set -eu

NS="${CHROMA_NAMESPACE:-fpp-data}"
POD="${CHROMA_POD:-chromadb-0}"
OUT="${1:-chroma-$(date +%F-%H%M%S).tgz}"

echo "Snapshotting $NS/$POD:/chroma/chroma -> $OUT"
kubectl -n "$NS" exec "$POD" -- tar czf - -C /chroma chroma > "$OUT"
echo "Wrote $OUT ($(wc -c < "$OUT") bytes)"
