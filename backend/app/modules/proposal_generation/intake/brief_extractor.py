"""Brief intake — infer the structured brief from a free-text query.

The composer is query-first: a user types *"draft a proposal for Apple Inc.'s
smart watch"* and the platform should understand **which company** and **what kind
of proposal** without making them fill a form. This extractor reads the query and
fills any brief field the caller left blank — entity, fiscal year, proposal type,
sector, line items.

Two guarantees keep it safe:

* **Explicit values always win.** The router only consults the inferred fields to
  fill gaps, so an Advanced-panel choice is never overridden, and the ACL /
  engagement context (security-critical, header-driven) is never touched here.
* **Inference is not grounding.** A guessed ``entity``/``fiscal_year`` still passes
  through the same metadata gate at retrieval (wrong-entity/wrong-period evidence
  is dropped), so a bad guess simply fails to ground — it can never fabricate
  evidence or rescue an un-grounded run.

It asks the bound LLM gateway for a strict JSON object (so it works with the local
Ollama model, air-gap-safe) and falls back to a conservative regex pass when the
model is unavailable or returns unparseable text (e.g. the Echo gateway in tests).
Any failure degrades to "infer nothing" — extraction must never block a run.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.domain.ports.llm_gateway import GenerationRequest, LLMGatewayPort

_SYSTEM = (
    "You extract structured fields from a request to write a business or financial "
    "proposal. Respond with ONLY a JSON object (no prose, no markdown fences) with "
    "exactly these keys:\n"
    '  "entity": the company/organisation the proposal is for (e.g. "Apple Inc."), '
    "or null if none is named;\n"
    '  "fiscal_year": a 4-digit integer if a year is stated, else null;\n'
    '  "proposal_type": a short snake_case label such as statement_of_work, pitch, '
    "or engagement_letter, or null if unclear;\n"
    '  "sector": e.g. banking, technology, healthcare, or null if unclear;\n'
    '  "line_items": an array of financial figures explicitly requested '
    '(e.g. ["revenue", "net income"]), or [] if none.\n'
    "Infer only what the text supports; use null or [] otherwise."
)

# Conservative regex fallbacks (used when the model can't be reached or returns junk).
_COMPANY_SUFFIX = (
    r"Inc|Incorporated|Corp|Corporation|Ltd|Limited|LLC|L\.L\.C|PLC|Co|Company|"
    r"Group|Holdings|Partners|AG|S\.A|N\.V|GmbH"
)
_ENTITY_WITH_SUFFIX = re.compile(
    r"\b([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3}\s+(?:" + _COMPANY_SUFFIX + r")\.?)",
)
_ENTITY_POSSESSIVE = re.compile(r"\b([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3})['’]s\b")
_ENTITY_FOR = re.compile(
    r"(?:proposal|sow|pitch|engagement|bid|tender)\s+(?:for|to)\s+"
    r"([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3})",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(?:FY[ ]?)?((?:19|20)\d{2})\b")


@dataclass(frozen=True, slots=True)
class InferredBrief:
    """Fields parsed from the query — every one optional, ``None``/empty = unknown."""

    entity: str | None = None
    fiscal_year: int | None = None
    proposal_type: str | None = None
    sector: str | None = None
    line_items: tuple[str, ...] = ()


class BriefExtractor:
    """Infer the structured brief from the composer's free-text query."""

    def __init__(self, gateway: LLMGatewayPort) -> None:
        self._gateway = gateway

    async def infer(self, query: str) -> InferredBrief:
        text = (query or "").strip()
        if not text:
            return InferredBrief()

        # Fast path: when the query plainly names a company ("Apple Inc.", "Tesla
        # Inc."), the regex resolves it with no model call — avoiding a slow CPU
        # round-trip before every generation. Only fall back to the LLM extractor
        # when the regex finds no entity.
        regex_entity = _regex_entity(text)
        regex_year = _regex_year(text)
        if regex_entity:
            return InferredBrief(entity=regex_entity, fiscal_year=regex_year)

        data = await self._ask_model(text) or {}
        return InferredBrief(
            entity=_clean_str(data.get("entity")),
            fiscal_year=regex_year or _clean_year(data.get("fiscal_year")),
            proposal_type=_clean_str(data.get("proposal_type")),
            sector=_clean_str(data.get("sector")),
            line_items=_clean_items(data.get("line_items")),
        )

    async def _ask_model(self, query: str) -> dict | None:
        """Ask the gateway for the JSON object; ``None`` on any failure (graceful)."""
        request = GenerationRequest(
            system=_SYSTEM,
            prompt=f'Request:\n"""{query}"""',
            max_output_tokens=200,
            temperature=0.0,
        )
        try:
            result = await self._gateway.generate(request)
        except Exception:  # noqa: BLE001 — never let extraction break generation
            return None
        return _parse_json_object(result.text)


# --- parsing helpers ---------------------------------------------------------


def _parse_json_object(text: str) -> dict | None:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def _clean_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or cleaned.lower() in {"null", "none", "n/a", "unknown"}:
        return None
    return cleaned


def _clean_year(value: object) -> int | None:
    try:
        year = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return year if 1900 <= year <= 2100 else None


def _clean_items(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, (list, tuple)):
        parts = [str(v) for v in value]
    else:
        return ()
    return tuple(p.strip() for p in parts if isinstance(p, str) and p.strip())


def _regex_entity(query: str) -> str | None:
    for pattern in (_ENTITY_WITH_SUFFIX, _ENTITY_FOR, _ENTITY_POSSESSIVE):
        match = pattern.search(query)
        if match:
            return match.group(1).strip(" .,'’")
    return None


def _regex_year(query: str) -> int | None:
    match = _YEAR.search(query)
    return int(match.group(1)) if match else None
