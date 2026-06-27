"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils/cn";

interface NavItem {
  href: string;
  label: string;
  glyph: string;
}

const NAV: NavItem[] = [
  { href: "/generate", label: "Generate", glyph: "✦" },
  { href: "/history", label: "Prompt History", glyph: "≣" },
  { href: "/metrics", label: "Metrics", glyph: "▦" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-surface">
      <div className="px-5 py-5">
        <div className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-white">
            ◆
          </span>
          <div className="leading-tight">
            <p className="text-sm font-semibold text-ink">Proposal Platform</p>
            <p className="text-[11px] text-muted">air-gapped · internal</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3">
        {NAV.map((item) => {
          let active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          // The Execution Report is a drill-in from History — keep History lit.
          if (item.href === "/history" && pathname.startsWith("/report")) active = true;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-accent/15 text-accent"
                  : "text-muted hover:bg-surface-2 hover:text-ink",
              )}
            >
              <span className="w-4 text-center">{item.glyph}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="px-5 py-4 text-[11px] leading-relaxed text-muted/70">
        Every figure is cited to the financial repository. Exemplars shape style,
        never numbers.
      </div>
    </aside>
  );
}
