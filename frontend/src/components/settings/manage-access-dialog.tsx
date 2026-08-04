"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { accountsApi } from "@/lib/api/accounts";
import { orgApi } from "@/lib/api/org";

const PLATFORM_LABEL: Record<string, string> = {
  meta: "Meta Ads",
  tiktok: "TikTok Ads",
  google_ads: "Google Ads",
  google_analytics: "Google Analytics",
};

interface Account {
  id: string;
  name: string;
  platform: string;
}

export function ManageAccessDialog({
  membershipId,
  memberName,
  open,
  onOpenChange,
}: {
  membershipId: string | null;
  memberName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  // All org accounts (owner sees all — this dialog is owner-only).
  const { data: accountsRes, isLoading: accountsLoading } = useQuery({
    queryKey: ["all-accounts"],
    queryFn: () => accountsApi.list({ per_page: 200 }),
    staleTime: 5 * 60 * 1000,
    enabled: open,
  });
  const accounts: Account[] = accountsRes?.data?.data ?? [];

  // Current grants for this member.
  const { data: grantsRes, isLoading: grantsLoading } = useQuery({
    queryKey: ["member-accounts", membershipId],
    queryFn: () => orgApi.memberAccounts(membershipId!),
    enabled: open && !!membershipId,
  });

  // Seed the checkboxes from the fetched grants whenever they (re)load.
  useEffect(() => {
    const ids = (grantsRes?.data?.data as { account_ids?: string[] } | undefined)?.account_ids;
    if (ids) setSelected(new Set(ids));
  }, [grantsRes]);

  const grouped = useMemo(() => {
    const g: Record<string, Account[]> = {};
    for (const a of accounts) (g[a.platform] ??= []).push(a);
    return g;
  }, [accounts]);

  const save = useMutation({
    mutationFn: () => orgApi.setMemberAccounts(membershipId!, [...selected]),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["member-accounts", membershipId] });
      onOpenChange(false);
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to save access.");
    },
  });

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const loading = accountsLoading || grantsLoading;

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) setError(null); onOpenChange(o); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Manage account access</DialogTitle>
          <DialogDescription>
            Choose which accounts <strong>{memberName}</strong> can see. They can only
            view the accounts you select here.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="max-h-[50vh] space-y-4 overflow-y-auto pr-1">
          {loading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-8 animate-pulse rounded bg-muted" />
              ))}
            </div>
          ) : accounts.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No accounts connected yet.
            </p>
          ) : (
            Object.entries(grouped).map(([platform, list]) => (
              <div key={platform} className="space-y-1.5">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {PLATFORM_LABEL[platform] ?? platform}
                </p>
                {list.map((a) => (
                  <label
                    key={a.id}
                    className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 hover:bg-muted"
                  >
                    <Checkbox
                      checked={selected.has(a.id)}
                      onCheckedChange={() => toggle(a.id)}
                    />
                    <span className="text-sm">{a.name}</span>
                  </label>
                ))}
              </div>
            ))
          )}
        </div>

        <DialogFooter className="items-center justify-between sm:justify-between">
          <span className="text-xs text-muted-foreground">
            {selected.size} account{selected.size === 1 ? "" : "s"} selected
          </span>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button disabled={save.isPending || loading} onClick={() => { setError(null); save.mutate(); }}>
              {save.isPending ? "Saving…" : "Save access"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
