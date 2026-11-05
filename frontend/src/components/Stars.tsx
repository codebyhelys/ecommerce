export function Stars({
  rating,
  count,
}: {
  rating: number | null;
  count: number;
}) {
  if (rating === null) {
    return <p className="h-4 text-xs text-zinc-400">Sem avaliações</p>;
  }
  const filled = Math.round(rating);
  return (
    <p
      className="flex h-4 items-center gap-1 text-xs text-zinc-500"
      aria-label={`Nota ${rating} de 5, ${count} avaliações`}
    >
      <span className="text-amber-500" aria-hidden>
        {"★".repeat(filled)}
        {"☆".repeat(5 - filled)}
      </span>
      ({count})
    </p>
  );
}
