import type { Metadata } from "next";
import { AuthForm } from "@/features/auth/auth-form";
import { localizedMetadata } from "@/lib/i18n/server";

export function generateMetadata(): Promise<Metadata> {
  return localizedMetadata("common.title.login");
}

export default function LoginRoute() {
  return <AuthForm />;
}
