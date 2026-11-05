import { cacheLife } from "next/cache";

// Endereço da API do backend. Só o servidor do Next lê esta variável (não vai para o navegador).
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8010/api";

export type Category = {
  id: number;
  name: string;
  slug: string;
  products_count?: number;
};

export type ProductImage = {
  id: number;
  image: string;
  alt_text: string;
  position: number;
};

export type Product = {
  id: number;
  name: string;
  slug: string;
  description: string;
  price: string; // a API manda o preço como texto ("49.90") para não perder centavos
  stock: number;
  category: Category;
  images: ProductImage[];
  reviews_count: number;
  rating_average: number | null;
};

// Formato das listas paginadas do Django REST Framework
type Page<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export async function getProducts(
  params: Record<string, string> = {},
): Promise<Product[]> {
  "use cache";
  cacheLife("minutes");

  try {
    const query = new URLSearchParams(params).toString();
    const res = await fetch(`${API_URL}/products/?${query}`);
    if (!res.ok) return [];
    const data: Page<Product> = await res.json();
    return data.results;
  } catch {
    return []; // API fora do ar: a vitrine fica vazia em vez de a página quebrar
  }
}

export async function getCategories(): Promise<Category[]> {
  "use cache";
  cacheLife("hours");

  try {
    const res = await fetch(`${API_URL}/categories/`);
    if (!res.ok) return [];
    return await res.json(); // categorias não são paginadas
  } catch {
    return [];
  }
}