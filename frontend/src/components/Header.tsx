import Link from "next/link";
import { getCategories } from "@/lib/api";

async function CategoryNav() {
  const categories = await getCategories();
  return (
    <nav aria-label="Categorias" className="border-t border-white/20 bg-brand-dark">
      <ul className="mx-auto flex max-w-7xl gap-5 overflow-x-auto px-4 py-2 text-sm text-white">
        {categories.map((category) => (
          <li key={category.id} className="shrink-0">
            <Link
              href={`/categorias/${category.slug}`}
              className="hover:underline"
            >
              {category.name}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function Header() {
  return (
    <header className="sticky top-0 z-50 bg-brand shadow">
      <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3">
        <Link href="/" className="text-2xl font-bold tracking-tight text-white">
          Loja
        </Link>

        <form action="/busca" role="search" className="flex flex-1">
          <label htmlFor="q" className="sr-only">
            Buscar produtos
          </label>
          <input
            id="q"
            name="q"
            type="search"
            placeholder="Buscar produtos, marcas e muito mais..."
            className="w-full rounded-l-md bg-white px-4 py-2 text-sm outline-none"
          />
          <button
            type="submit"
            className="rounded-r-md bg-zinc-900 px-4 text-sm font-medium text-white hover:bg-zinc-700"
          >
            Buscar
          </button>
        </form>

        <nav aria-label="Conta" className="flex items-center gap-4 text-sm text-white">
          <Link href="/entrar" className="hover:underline">
            Entrar
          </Link>
          <Link href="/carrinho" className="font-medium hover:underline">
            Carrinho
          </Link>
        </nav>
      </div>
      <CategoryNav />
    </header>
  );
}