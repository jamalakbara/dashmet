import { redirect } from "next/navigation";

// Root → redirect to overview dashboard
export default function RootPage() {
  redirect("/overview");
}
