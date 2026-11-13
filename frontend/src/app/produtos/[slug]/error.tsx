"use client"; // páginas de erro precisam ser Client Components

import { useEffect } from "react";

export default function ProductError({
  error,
  retry,
}: {
  error: unknown;
  retry: () => void;
}) {
  useEffect(() => {
    console.error(error); // depois: enviar para um serviço de monitoramento
  }, [error]);

  return (
    <div className="mx-auto max-w-xl px-4 py-20 text-center">
      <h1 className="text-2xl font-semibold">Não foi possível carregar o produto</h1>
      <p className="mt-2 text-zinc-600">
        Tivemos um problema do nosso lado. Tente de novo em instantes.
      </p>
      <button
        type="button"
        onClick={() => retry()}
        className="mt-6 rounded-md bg-brand px-6 py-3 font-semibold text-white hover:bg-brand-dark"
      >
        Tentar de novo
      </button>
    </div>
  );
}