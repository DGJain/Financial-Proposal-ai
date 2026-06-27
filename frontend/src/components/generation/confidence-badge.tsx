import { Badge, type Tone } from "@/components/ui/badge";
import type { ConfidenceBand } from "@/types/api";

const BAND_TONE: Record<ConfidenceBand, Tone> = {
  high: "success",
  medium: "warn",
  low: "danger",
};

export function ConfidenceBadge({ band, score }: { band: ConfidenceBand; score: number }) {
  return (
    <Badge tone={BAND_TONE[band]}>
      <span className="uppercase">{band}</span>
      <span className="font-mono opacity-80">{score.toFixed(2)}</span>
    </Badge>
  );
}
