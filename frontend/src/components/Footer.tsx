import { cacheLife } from "next/cache";
import Link from "next/link";

const columns = [
  {
    title: "Ajuda",
    links: ["Central de ajuda", "Como comprar", "Trocas e devoluções", "Fale conosco"],
  },
  {
    title: "Institucional",
    links: ["Sobre nós", "Política de privacidade", "Termos de uso"],
  },
  {
    title: "Pagamento",
    links: ["Pix", "Cartão de crédito", "Boleto"],
  },
];

// A data muda com o tempo; o Next exige que isso seja explícito: aqui o resultado é guardado por 1 dia.
async function Copyright() {
  "use cache";
  cacheLife("days");

  return (
    <p className="border-t border-white/10 py-4 text-center text-xs">
      © {new Date().getFullYear()} Loja. Todos os direitos reservados.
    </p>
  );
}

export function Footer() {
  return (
    <footer className="mt-10 bg-zinc-900 text-zinc-300">
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <p className="text-xl font-bold text-white">Loja</p>
          <p className="mt-2 text-sm">
            Compre com segurança, receba em casa e pague como preferir.
          </p>
        </div>
        {columns.map((column) => (
          <div key={column.title}>
            <h2 className="font-semibold text-white">{column.title}</h2>
            <ul className="mt-3 space-y-2 text-sm">
              {column.links.map((label) => (
                <li key={label}>
                  <Link href="#" className="hover:text-white hover:underline">
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <Copyright />
    </footer>
  );
}