import type { Metadata } from "next";
import { AuthForm } from "@/features/auth/auth-form";
import { localizedMetadata } from "@/lib/i18n/server";

export function generateMetadata(): Promise<Metadata> {
  return localizedMetadata("common.title.register");
}

export default function RegisterRoute() {
  return <AuthForm register />;
}
