import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { ProductGallery } from "@/components/ProductGallery";
import { ProductSkeleton } from "@/components/ProductSkeleton";
import { Stars } from "@/components/Stars";
import { getProduct } from "@/lib/api";
import { formatPrice, installment } from "@/lib/format";

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const product = await getProduct(slug);
  if (!product) return { title: "Produto não encontrado" };
  return {
    title: product.name,
    description: product.description.slice(0, 155),
  };
}

async function ProductDetails({ params }: Props) {
  const { slug } = await params;
  const product = await getProduct(slug);
  if (!product) notFound();

  const parcels = installment(product.price);
  const available = product.stock > 0;

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <nav aria-label="Você está em" className="mb-4 text-sm text-zinc-500">
        <Link href="/" className="hover:underline">
          Início
        </Link>
        {" / "}
        <Link
          href={`/categorias/${product.category.slug}`}
          className="hover:underline"
        >
          {product.category.name}
        </Link>
      </nav>

      <div className="grid gap-8 lg:grid-cols-2">
        <ProductGallery images={product.images} name={product.name} />

        <section className="rounded-lg border border-zinc-200 bg-white p-6">
          <h1 className="text-2xl font-semibold">{product.name}</h1>
          <div className="mt-2">
            <Stars
              rating={product.rating_average}
              count={product.reviews_count}
            />
          </div>

          <p className="mt-6 text-4xl font-bold">{formatPrice(product.price)}</p>
          {parcels && <p className="mt-1 text-green-700">{parcels}</p>}

          <p
            className={`mt-4 text-sm font-medium ${available ? "text-green-700" : "text-red-600"}`}
          >
            {!available
              ? "Produto indisponível"
              : product.stock <= 5
                ? `Restam apenas ${product.stock} unidades`
                : "Em estoque"}
          </p>

          <button
            type="button"
            disabled
            className="mt-6 w-full rounded-md bg-brand px-6 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            Adicionar ao carrinho
          </button>
          <p className="mt-2 text-xs text-zinc-500">
            O carrinho será ligado em uma das próximas aulas.
          </p>
        </section>
      </div>

      <section className="mt-8 rounded-lg border border-zinc-200 bg-white p-6">
        <h2 className="text-lg font-semibold">Descrição</h2>
        <p className="mt-2 whitespace-pre-line text-zinc-700">
          {product.description}
        </p>
      </section>
    </div>
  );
}

export default function ProductPage({ params }: Props) {
  return (
    <Suspense fallback={<ProductSkeleton />}>
      <ProductDetails params={params} />
    </Suspense>
  );
}