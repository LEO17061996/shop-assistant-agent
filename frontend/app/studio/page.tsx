import type { Metadata } from "next";
import { Studio } from "@/components/Studio";

export const metadata: Metadata = {
  title: "Listing Studio — Kestrel Home",
  description: "Product photo to marketplace listing, SEO and Meta ads, with rule checks and visual search.",
};

export default function StudioPage() {
  return <Studio />;
}
