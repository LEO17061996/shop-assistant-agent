import Image from "next/image";
import { money, type Product } from "@/lib/api";

export function ProductCard({ p, index }: { p: Product; index: number }) {
  const inStock = p.stock > 0;
  return (
    <article
      className="rise group flex w-[200px] shrink-0 flex-col overflow-hidden rounded-[3px] border border-rule bg-card shadow-[0_1px_0_var(--rule)] transition hover:-translate-y-0.5 hover:shadow-[0_8px_24px_-12px_rgba(60,40,20,0.35)]"
      style={{ animationDelay: `${index * 70}ms` }}
    >
      <div className="relative aspect-[4/3] bg-paper-2">
        <Image
          src={p.image_url}
          alt={p.name}
          fill
          unoptimized
          sizes="200px"
          className="object-contain p-3 mix-blend-multiply dark:mix-blend-normal"
        />
        <span className="absolute left-2 top-2 rounded-full bg-card/90 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-ink-2">
          {p.category}
        </span>
      </div>
      <div className="flex flex-1 flex-col gap-2 p-3">
        <h4 className="line-clamp-2 font-display text-[15px] leading-snug">{p.name}</h4>
        <div className="mt-auto flex items-baseline justify-between gap-2">
          <span className="font-mono text-[15px] font-medium">{money(p.price_usd)}</span>
          <span className={`text-[11px] ${inStock ? "text-olive" : "text-danger"}`}>
            {inStock ? `${p.stock} in stock` : "Out of stock"}
          </span>
        </div>
        <div className="flex gap-1">
          {["US", "UK"].map((c) => (
            <span
              key={c}
              className={`rounded-sm border px-1.5 font-mono text-[10px] ${
                p.ships_to.includes(c)
                  ? "border-olive/40 bg-olive-soft text-olive"
                  : "border-rule text-ink-3 line-through"
              }`}
            >
              {c}
            </span>
          ))}
          <span className="ml-auto self-center font-mono text-[10px] text-ink-3">{p.id}</span>
        </div>
      </div>
    </article>
  );
}
