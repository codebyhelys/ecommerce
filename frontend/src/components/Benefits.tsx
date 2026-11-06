const benefits = [
  { title: "Frete grátis", text: "Em compras acima de R$ 299" },
  { title: "Até 6x sem juros", text: "No cartão de crédito" },
  { title: "Compra segura", text: "Seus dados protegidos" },
  { title: "Troca fácil", text: "Em até 7 dias" },
];

export function Benefits() {
  return (
    <section className="border-b border-zinc-200 bg-white">
      <ul className="mx-auto grid max-w-7xl grid-cols-2 gap-4 px-4 py-4 text-sm lg:grid-cols-4">
        {benefits.map((benefit) => (
          <li key={benefit.title}>
            <p className="font-semibold">{benefit.title}</p>
            <p className="text-zinc-500">{benefit.text}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}