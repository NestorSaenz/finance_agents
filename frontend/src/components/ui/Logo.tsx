import { LineChart } from "lucide-react";

interface LogoProps {
  /** Show the "Safi" wordmark next to the mark. */
  withWordmark?: boolean;
  className?: string;
}

export function Logo({ withWordmark = true, className = "" }: LogoProps) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-positive text-white shadow-sm">
        <LineChart className="h-5 w-5" aria-hidden />
      </span>
      {withWordmark && (
        <span className="text-lg font-semibold tracking-tight text-ink">Safi</span>
      )}
    </span>
  );
}
