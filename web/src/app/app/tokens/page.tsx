import type { Metadata } from "next";
import { TokensPage } from "@/features/tokens/tokens-page";
import { localizedMetadata } from "@/lib/i18n/server";

export function generateMetadata(): Promise<Metadata> {
  return localizedMetadata("common.title.tokens");
}

export default function TokensRoute() {
  return <TokensPage />;
}
