"use client";

import { BentoTile } from "./bento-tile";
import { useMe } from "@/hooks/use-me";
import { useAccountsCount } from "@/hooks/use-account";

/** Greeting tile — a big display hello + a plain workspace status line. */
export function GreetingTile({ className }: { className?: string }) {
  const accountCount = useAccountsCount();

  const { data: me } = useMe();

  const firstName = me?.name?.split(" ")[0] ?? "there";
  const orgName = me?.org?.name ?? "your workspace";
  const count = accountCount ?? 0;
  const status = `${count} account${count === 1 ? "" : "s"} connected · ${orgName}`;

  return (
    <BentoTile className={className}>
      <div className="flex flex-1 flex-col justify-between gap-4 p-4">
        <div className="font-display text-3xl font-semibold leading-tight sm:text-4xl">
          Hello,
          <br />
          <span className="text-primary">{firstName}</span>
        </div>
        <p className="text-sm text-muted-foreground">{status}</p>
      </div>
    </BentoTile>
  );
}
