// Retângulos cinza enquanto o produto carrega: o layout não "pula" quando os dados chegam.
export function ProductSkeleton() {
  return (
    <div className="mx-auto grid max-w-7xl animate-pulse gap-8 px-4 py-8 lg:grid-cols-2">
      <div className="aspect-square rounded-lg bg-zinc-200" />
      <div className="space-y-4">
        <div className="h-8 w-3/4 rounded bg-zinc-200" />
        <div className="h-4 w-1/3 rounded bg-zinc-200" />
        <div className="h-10 w-1/2 rounded bg-zinc-200" />
        <div className="h-12 w-full rounded bg-zinc-200" />
      </div>
    </div>
  );
}
