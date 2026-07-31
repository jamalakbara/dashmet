import { redirect } from "next/navigation";

// Root → redirect to combined dashboard
export default function RootPage() {
  redirect("/dashboard");
}
