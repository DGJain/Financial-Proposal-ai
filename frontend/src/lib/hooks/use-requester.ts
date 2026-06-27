"use client";

import { useCallback, useEffect, useState } from "react";

import type { RequesterContext } from "@/types/api";

const STORAGE_KEY = "fpp.requester";

// Demo defaults match the seeded local backend so generation grounds out of the box.
const DEFAULTS: RequesterContext = {
  engagementId: "eng-1",
  aclGroups: "consultants",
  requestedBy: "analyst-1",
};

/**
 * The caller's ACL/engagement context, persisted in localStorage so the deal-team
 * wall is applied consistently across Generate, Upload, and Edit. In a real
 * deployment this comes from the authenticated session, not a form.
 */
export function useRequester(): {
  requester: RequesterContext;
  setRequester: (next: RequesterContext) => void;
} {
  const [requester, setState] = useState<RequesterContext>(DEFAULTS);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) setState({ ...DEFAULTS, ...JSON.parse(raw) });
    } catch {
      // ignore malformed/unavailable storage — fall back to defaults
    }
  }, []);

  const setRequester = useCallback((next: RequesterContext) => {
    setState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // non-fatal: context simply won't persist across reloads
    }
  }, []);

  return { requester, setRequester };
}
