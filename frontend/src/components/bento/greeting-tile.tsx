"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useReducedMotion } from "framer-motion";
import { Terminal } from "lucide-react";
import { BentoTile } from "./bento-tile";
import { authApi } from "@/lib/api/auth";
import { queryKeys } from "@/lib/query-keys";
import { useAccountsCount } from "@/hooks/use-account";

interface Me {
  id: string;
  name: string;
  email: string;
  org: { id: string; name: string; slug: string; role: string };
}

function useTypewriter(full: string, speed = 26, enabled = true) {
  const [text, setText] = useState(enabled ? "" : full);
  useEffect(() => {
    if (!enabled) {
      setText(full);
      return;
    }
    setText("");
    let i = 0;
    const id = setInterval(() => {
      i += 1;
      setText(full.slice(0, i));
      if (i >= full.length) clearInterval(id);
    }, speed);
    return () => clearInterval(id);
  }, [full, enabled, speed]);
  return text;
}

/** Terminal-style greeting tile — big display hello + a typed mono status line. */
export function GreetingTile({ className }: { className?: string }) {
  const reduce = useReducedMotion();
  const accountCount = useAccountsCount();

  const { data: me } = useQuery({
    queryKey: queryKeys.me(),
    queryFn: async () => (await authApi.me()).data.data as Me,
    staleTime: 60 * 60 * 1000,
  });

  const firstName = me?.name?.split(" ")[0] ?? "there";
  const orgName = me?.org?.name ?? "your workspace";
  const line = `> ${accountCount ?? 0} accounts connected · ${orgName}. terminal open._`;
  const typed = useTypewriter(line, 22, !reduce);

  return (
    <BentoTile label="Session" icon={Terminal} className={className}>
      <div className="flex flex-1 flex-col justify-between gap-4 p-4">
        <div className="font-display text-3xl font-semibold leading-tight sm:text-4xl">
          Hello,
          <br />
          <span className="text-primary">{firstName}</span>
        </div>
        <div className="min-h-4 font-mono text-[11px] leading-relaxed text-muted-foreground">
          {typed}
          <span className="ml-0.5 inline-block h-3 w-1.5 translate-y-0.5 animate-pulse bg-primary/70" />
        </div>
      </div>
    </BentoTile>
  );
}
