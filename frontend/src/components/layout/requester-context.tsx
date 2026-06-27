"use client";

import { Card, CardBody } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/field";
import type { RequesterContext } from "@/types/api";

/**
 * Editor for the caller's ACL/engagement context. In production this is the
 * authenticated session; here it is editable so the deal-team wall can be
 * demonstrated (switching engagement makes evidence invisible → a refusal).
 */
export function RequesterContextCard({
  requester,
  onChange,
}: {
  requester: RequesterContext;
  onChange: (next: RequesterContext) => void;
}) {
  const set = (patch: Partial<RequesterContext>) => onChange({ ...requester, ...patch });
  return (
    <Card>
      <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Field label="Engagement ID" hint="deal-team wall">
          <Input
            value={requester.engagementId ?? ""}
            onChange={(e) => set({ engagementId: e.target.value })}
            placeholder="eng-1"
          />
        </Field>
        <Field label="ACL groups" hint="comma-separated">
          <Input
            value={requester.aclGroups ?? ""}
            onChange={(e) => set({ aclGroups: e.target.value })}
            placeholder="consultants"
          />
        </Field>
        <Field label="Requested by">
          <Input
            value={requester.requestedBy ?? ""}
            onChange={(e) => set({ requestedBy: e.target.value })}
            placeholder="analyst-1"
          />
        </Field>
      </CardBody>
    </Card>
  );
}
