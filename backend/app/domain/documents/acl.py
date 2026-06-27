"""Access-control value object carried from ingestion into every retrieval.

ACL/ABAC is applied **as a retrieval pre-filter** (ARCHITECTURE_SUMMARY.md
"Security Constraints"). The tags are stamped on a document at ingestion and
copied onto every chunk, then matched against the caller's grants before any
vector search runs — cross-engagement / deal-team walls are enforced here, not
after the fact.

This is a pure domain value object: it models *what* access requires, never
*how* identity is resolved (that lives in ``core.security``).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AccessControl:
    """Document/chunk access requirements.

    - ``acl_groups``: RBAC groups permitted to retrieve the content.
    - ``engagement_id``: deal-team wall — content is scoped to one engagement.
    - ``classification``: handling label (e.g. ``internal``, ``confidential``,
      ``restricted``) that may further constrain retrieval.
    """

    acl_groups: frozenset[str] = field(default_factory=frozenset)
    engagement_id: str | None = None
    classification: str | None = None

    def permits(
        self,
        *,
        caller_groups: frozenset[str],
        caller_engagement_id: str | None,
    ) -> bool:
        """Whether a caller with the given grants may retrieve this content.

        Fail-closed: an engagement-scoped item is invisible outside its
        engagement, and group membership must intersect when groups are set.
        """
        if self.engagement_id is not None and self.engagement_id != caller_engagement_id:
            return False
        if self.acl_groups and self.acl_groups.isdisjoint(caller_groups):
            return False
        return True
