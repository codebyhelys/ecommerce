import Link from "next/link";
import { getCategories } from "@/lib/api";

export async function CategoryStrip() {
  const categories = await getCategories();
  if (categories.length === 0) return null;

  return (
    <section className="mx-auto max-w-7xl px-4 py-6">
      <h2 className="mb-3 text-xl font-semibold">Compre por categoria</h2>
      <ul className="flex gap-4 overflow-x-auto pb-2">
        {categories.map((category) => (
          <li key={category.id} className="shrink-0">
            <Link
              href={`/categorias/${category.slug}`}
              className="flex w-24 flex-col items-center gap-2 text-center text-sm hover:text-brand"
            >
              <span className="flex size-16 items-center justify-center rounded-full bg-white text-2xl font-bold text-brand shadow">
                {category.name.charAt(0)}
              </span>
              {category.name}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
