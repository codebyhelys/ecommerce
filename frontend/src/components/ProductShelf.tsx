import Link from "next/link";
import { getProducts } from "@/lib/api";
import { ProductCard } from "./ProductCard";

export async function ProductShelf({
  title,
  href,
  params,
}: {
  title: string;
  href: string;
  params: Record<string, string>;
}) {
  const products = await getProducts(params);
  if (products.length === 0) return null; // prateleira vazia não aparece

  return (
    <section className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-xl font-semibold">{title}</h2>
        <Link href={href} className="text-sm font-medium text-brand hover:underline">
          Ver tudo
        </Link>
      </div>
      <div className="flex snap-x gap-3 overflow-x-auto pb-2">
        {products.slice(0, 12).map((product) => (
          <ProductCard key={product.id} product={product} />
        ))}
      </div>
    </section>
  );
}
