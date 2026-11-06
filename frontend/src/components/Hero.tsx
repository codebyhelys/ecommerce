import Link from "next/link";

export function Hero() {
  return (
    <section className="bg-linear-to-r from-brand to-orange-400 text-white">
      <div className="mx-auto flex max-w-7xl flex-col items-start gap-4 px-4 py-14 sm:py-20">
        <p className="text-sm font-medium uppercase tracking-widest">
          Ofertas da semana
        </p>
        <h1 className="max-w-xl text-3xl font-bold leading-tight sm:text-5xl">
          Até 40% de desconto e frete grátis acima de R$ 299
        </h1>
        <Link
          href="/busca?ordering=price"
          className="rounded-md bg-white px-6 py-3 font-semibold text-brand-dark hover:bg-zinc-100"
        >
          Ver ofertas
        </Link>
      </div>
    </section>
  );
}
