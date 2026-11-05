import Image from "next/image";
import Link from "next/link";
import type { Product } from "@/lib/api";
import { formatPrice, installment } from "@/lib/format";
import { Stars } from "./Stars";

export function ProductCard({ product }: { product: Product }) {
  const photo = product.images[0];
  const parcels = installment(product.price);

  return (
    <Link
      href={`/produtos/${product.slug}`}
      className="group flex w-44 shrink-0 snap-start flex-col rounded-lg border border-zinc-200 bg-white p-3 transition hover:shadow-md sm:w-52"
    >
      <div className="relative aspect-square overflow-hidden rounded-md bg-zinc-100">
        {photo ? (
          <Image
            src={photo.image}
            alt={photo.alt_text || product.name}
            fill
            sizes="(min-width: 640px) 208px, 176px"
            className="object-cover transition group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-zinc-400">
            Sem foto
          </div>
        )}
      </div>

      <h3 className="mt-3 line-clamp-2 min-h-10 text-sm text-zinc-800">
        {product.name}
      </h3>
      <Stars rating={product.rating_average} count={product.reviews_count} />
      <p className="mt-1 text-xl font-semibold text-zinc-900">
        {formatPrice(product.price)}
      </p>
      <p className="h-4 text-xs text-green-700">{parcels}</p>
    </Link>
  );
}