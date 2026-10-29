import { AuthForm } from "@/features/auth/auth-form";

export const metadata = { title: "注册" };

export default function RegisterRoute() {
  return <AuthForm register />;
}
