interface Props {
  level: "high" | "medium" | "low" | "watching";
}

const styles: Record<string, string> = {
  high: "bg-accent-green/15 text-accent-green",
  medium: "bg-accent-gold/15 text-accent-gold",
  low: "bg-accent-red/15 text-accent-red",
  watching: "bg-bg-cell text-text-secondary",
};

const labels: Record<string, string> = {
  high: "High Conviction",
  medium: "Medium Conviction",
  low: "Low Conviction",
  watching: "Watching",
};

export default function ConvictionBadge({ level }: Props) {
  return (
    <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium ${styles[level]}`}>
      {labels[level]}
    </span>
  );
}
