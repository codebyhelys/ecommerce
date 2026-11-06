import { Benefits } from "@/components/Benefits";
import { CategoryStrip } from "@/components/CategoryStrip";
import { Hero } from "@/components/Hero";
import { ProductShelf } from "@/components/ProductShelf";

export default function Home() {
  return (
    <>
      <Hero />
      <Benefits />
      <CategoryStrip />
      <ProductShelf
        title="Lançamentos"
        href="/busca?ordering=-created_at"
        params={{ ordering: "-created_at" }}
      />
      <ProductShelf
        title="Menores preços"
        href="/busca?ordering=price"
        params={{ ordering: "price" }}
      />
    </>
  );
}