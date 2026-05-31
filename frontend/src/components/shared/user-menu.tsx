"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { LogOut, Settings, User } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { authApi } from "@/lib/api/auth";
import { clearAuthCookie } from "@/lib/api/client";
import { queryKeys } from "@/lib/query-keys";

interface Me {
  id: string;
  name: string;
  email: string;
  org: { id: string; name: string; slug: string; role: string };
}

export function UserMenu() {
  const router = useRouter();

  const { data: me } = useQuery({
    queryKey: queryKeys.me(),
    queryFn: async () => {
      const res = await authApi.me();
      return res.data.data as Me;
    },
    staleTime: 60 * 60 * 1000,
  });

  const initials = me?.name
    ? me.name.split(" ").map((n) => n[0]).join("").toUpperCase().slice(0, 2)
    : "?";

  async function handleSignOut() {
    await authApi.logout().catch(() => {});
    clearAuthCookie();
    router.push("/login");
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <Avatar>
          <AvatarFallback className="text-xs font-medium">{initials}</AvatarFallback>
        </Avatar>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <div className="flex flex-col gap-0.5 px-1.5 py-1">
          <span className="text-sm font-medium">{me?.name ?? "—"}</span>
          <span className="text-xs text-muted-foreground truncate">{me?.email ?? "—"}</span>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => router.push("/settings/org")}>
          <Settings className="size-4" />
          Settings
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onSelect={handleSignOut}>
          <LogOut className="size-4" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
