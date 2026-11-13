import Link from "next/link";

export default function ProductNotFound() {
  return (
    <div className="mx-auto max-w-xl px-4 py-20 text-center">
      <h1 className="text-2xl font-semibold">Produto não encontrado</h1>
      <p className="mt-2 text-zinc-600">
        Ele pode ter saído de linha ou o endereço está errado.
      </p>
      <Link
        href="/"
        className="mt-6 inline-block rounded-md bg-brand px-6 py-3 font-semibold text-white hover:bg-brand-dark"
      >
        Voltar para a loja
      </Link>
    </div>
  );
}