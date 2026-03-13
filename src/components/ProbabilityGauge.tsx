interface Props {
  value: number;
  size?: number;
}

export default function ProbabilityGauge({ value }: Props) {
  const width = 10;
  const filled = Math.round((value / 100) * width);
  const bar = "[" + "|".repeat(filled) + ".".repeat(width - filled) + "]";
  const color = value > 50 ? "text-accent-green" : "text-accent-red";

  return (
    <span className={`text-[10px] font-bold ${color}`}>
      {bar} {value}%
    </span>
  );
}
