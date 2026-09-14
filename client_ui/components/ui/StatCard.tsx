export function StatCard({
  label,
  value,
  sub,
  subTone = "muted",
  highlight = false,
}: {
  label: string;
  value: string;
  sub?: string;
  subTone?: "muted" | "positive" | "negative";
  highlight?: boolean;
}) {
  const subColor =
    subTone === "positive"
      ? "text-positive"
      : subTone === "negative"
        ? "text-negative"
        : highlight
          ? "text-white/85"
          : "text-text-muted";

  return (
    <div
      className={`rounded-xl p-[18px] ${
        highlight
          ? "bg-accent text-white"
          : "border border-border bg-surface"
      }`}
    >
      <p className={`text-xs ${highlight ? "text-white/85" : "text-text-muted"}`}>
        {label}
      </p>
      <p
        className={`mt-1.5 text-[26px] font-semibold ${
          highlight ? "text-white" : "text-text-primary"
        }`}
      >
        {value}
      </p>
      {sub && <p className={`mt-1.5 text-xs ${subColor}`}>{sub}</p>}
    </div>
  );
}
