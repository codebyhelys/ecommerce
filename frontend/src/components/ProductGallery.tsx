import Image from "next/image";
import type { ProductImage } from "@/lib/api";

export function ProductGallery({
  images,
  name,
}: {
  images: ProductImage[];
  name: string;
}) {
  const [main, ...others] = images;

  return (
    <div>
      <div className="relative aspect-square overflow-hidden rounded-lg border border-zinc-200 bg-zinc-100">
        {main ? (
          <Image
            src={main.image}
            alt={main.alt_text || name}
            fill
            preload
            sizes="(min-width: 1024px) 560px, 100vw"
            className="object-cover"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-zinc-400">
            Sem foto
          </div>
        )}
      </div>

      {others.length > 0 && (
        <ul className="mt-3 flex gap-3 overflow-x-auto">
          {others.map((image) => (
            <li
              key={image.id}
              className="relative size-20 shrink-0 overflow-hidden rounded-md border border-zinc-200"
            >
              <Image
                src={image.image}
                alt={image.alt_text || name}
                fill
                sizes="80px"
                className="object-cover"
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}