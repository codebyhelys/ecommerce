const brl = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

export function formatPrice(value: string | number): string {
  return brl.format(Number(value));
}

// Parcelamento só para exibir na vitrine; as regras reais virão do backend/gateway.
export function installment(value: string, times = 6): string | null {
  const price = Number(value);
  if (price < 60) return null;
  return `${times}x de ${formatPrice(price / times)} sem juros`;
}