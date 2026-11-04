import { localizedMetadata } from "@/lib/i18n/server";
import { TemplatesPage } from "@/features/templates/templates-page";

export function generateMetadata() {
  return localizedMetadata("common.title.templates");
}

export default function TemplatesRoute() {
  return <TemplatesPage />;
}
