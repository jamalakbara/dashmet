"use client";

import { useRouter } from "next/navigation";
import { LogOut, Settings } from "lucide-react";
import { AnimatedIcon } from "@/components/shared/animated-icon";
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
import { useMe } from "@/hooks/use-me";

export function UserMenu() {
  const router = useRouter();

  const { data: me } = useMe();

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
        <DropdownMenuItem className="group" onClick={() => router.push("/settings/org")}>
          <AnimatedIcon icon={Settings} motionPreset="spin" iconClassName="size-4" />
          Settings
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem className="group" variant="destructive" onClick={handleSignOut}>
          <AnimatedIcon icon={LogOut} motionPreset="nudgeRight" iconClassName="size-4" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
