"use client";

import { Suspense, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { formatDistanceToNow } from "date-fns";
import { CheckCircle2, XCircle, Plug, ExternalLink, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { AnimatedIcon } from "@/components/shared/animated-icon";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { connectionsApi } from "@/lib/api/connections";
import { accountsApi } from "@/lib/api/accounts";
import { syncApi } from "@/lib/api/sync";
import { queryKeys } from "@/lib/query-keys";
import { useIsOwner } from "@/hooks/use-role";

const tokenSchema = z.object({
  access_token: z.string().min(10, "Token is too short"),
});
type TokenForm = z.infer<typeof tokenSchema>;

interface Connection {
  id: string;
  platform: string;
  is_active: boolean;
  token_type?: string;
  connected_by?: string;
  connected_at?: string;
  last_used_at?: string;
  scopes?: string[];
}

const PLATFORMS = [
  {
    key:       "meta",
    name:      "Meta Ads",
    icon:      "M",
    color:     "bg-blue-600",
    auth_type: "token" as const,
    instructions: `Create a System User token in Meta Business Manager:
1. Go to Business Settings → Users → System Users
2. Create or select a System User with "Ads" access
3. Click "Generate Token" and select the required permissions:
   • ads_management, ads_read, read_insights
4. Paste the generated token below.`,
  },
  {
    key:       "tiktok",
    name:      "TikTok Ads",
    icon:      "T",
    color:     "bg-black",
    auth_type: "oauth" as const,
    instructions: undefined,
  },
  {
    key:       "google_ads",
    name:      "Google Ads",
    icon:      "G",
    color:     "bg-red-500",
    auth_type: "oauth" as const,
    instructions: undefined,
  },
];

// Brand SVGs served from /public; platforms without one fall back to a letter tile.
const PLATFORM_LOGO: Record<string, string> = {
  meta:       "/meta-logo.svg",
  tiktok:     "/tiktok-logo.svg",
  google_ads: "/gads-logo.svg",
};

function PlatformIcon({ platform }: { platform: typeof PLATFORMS[0] }) {
  const logo = PLATFORM_LOGO[platform.key];
  if (logo) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={logo} alt={platform.name} className="size-10 shrink-0 rounded-lg" />;
  }
  return (
    <div className={`flex size-10 shrink-0 items-center justify-center rounded-lg ${platform.color} text-sm font-bold text-white`}>
      {platform.icon}
    </div>
  );
}

function SyncProgressBanner({ platformKey, platformName, onDismiss }: {
  platformKey: string;
  platformName: string;
  onDismiss: () => void;
}) {
  const { data: accounts = [] } = useQuery({
    queryKey: queryKeys.accounts(),
    queryFn: async () => {
      const res = await accountsApi.list();
      return res.data.data as { id: string; platform: string; account_status: string }[];
    },
    // poll until we find an account for this platform
    refetchInterval: (query) => {
      const data = query.state.data ?? [];
      const found = data.some((a: { platform: string; account_status: string }) =>
        a.platform === platformKey && a.account_status === "active"
      );
      return found ? false : 5000;
    },
    staleTime: 0,
  });

  const account = accounts.find(a => a.platform === platformKey && a.account_status === "active");
  const accountId = account?.id;

  const { data: statusRes } = useQuery({
    queryKey: queryKeys.syncStatus(accountId ?? ""),
    queryFn: () => syncApi.status(accountId!),
    enabled: !!accountId,
    refetchInterval: 5000, // poll real job status every 5s
    staleTime: 0, // always refetch — this is a live progress view
  });

  const jobs: Record<string, { status: string }> = statusRes?.data?.data?.jobs ?? {};

  const stages = [
    { label: "Accounts imported", done: !!accountId },
    { label: "Campaigns & ads structure", time: "~1–3 min", done: jobs.structure?.status === "completed" },
    { label: "Last 7 days metrics", time: "~2–8 min", done: jobs.insights_daily?.status === "completed" },
    {
      label: "Historical data (14d / 30d / 90d)",
      time: "~3–15 min",
      done: platformKey === "tiktok" || platformKey === "google_ads"
        ? jobs.insights_historical?.status === "completed"
        : jobs.insights_async?.status === "completed",
    },
  ];

  const allDone = stages.every(s => s.done);

  useEffect(() => {
    if (!allDone) return;
    const t = setTimeout(onDismiss, 3000);
    return () => clearTimeout(t);
  }, [allDone, onDismiss]);

  return (
    <Alert>
      <AlertDescription>
        <div className="flex items-start justify-between gap-2">
          <div className="space-y-2">
            <p className="font-medium text-sm">
              {allDone ? `${platformName} sync complete!` : `Syncing ${platformName} data…`}
            </p>
            <div className="space-y-1">
              {stages.map((stage, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  {stage.done
                    ? <AnimatedIcon
                        icon={CheckCircle2}
                        motionPreset="pop"
                        trigger="state"
                        appear
                        activeVariant="show"
                        className="shrink-0"
                        iconClassName="size-3 text-green-500"
                      />
                    : <Loader2 className="size-3 shrink-0 animate-spin text-muted-foreground" />
                  }
                  <span>{stage.label}</span>
                  {!stage.done && stage.time && (
                    <span className="text-muted-foreground">— ready in {stage.time}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
          <button onClick={onDismiss} className="group shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground">
            <AnimatedIcon icon={X} motionPreset="wiggle" iconClassName="size-3.5" />
          </button>
        </div>
      </AlertDescription>
    </Alert>
  );
}

function ConnectionsSettingsPageInner() {
  const qc = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const isOwner = useIsOwner();
  const [connectingPlatform, setConnectingPlatform] = useState<typeof PLATFORMS[0] | null>(null);
  const [disconnectId, setDisconnectId] = useState<string | null>(null);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [connectSuccess, setConnectSuccess] = useState(false);
  const [oauthLoading, setOauthLoading] = useState(false);
  const [syncBannerPlatform, setSyncBannerPlatform] = useState<{ key: string; name: string } | null>(null);

  // Handle return from TikTok OAuth callback
  useEffect(() => {
    const tiktokStatus = searchParams.get("tiktok");
    if (tiktokStatus === "connected") {
      qc.invalidateQueries({ queryKey: ["connections"] });
      qc.invalidateQueries({ queryKey: queryKeys.accounts() });
      toast.success("TikTok connected. Syncing your data…");
      setConnectSuccess(true);
      setSyncBannerPlatform({ key: "tiktok", name: "TikTok Ads" });
      setTimeout(() => setConnectSuccess(false), 4000);
      const checkAfter = (ms: number) =>
        setTimeout(async () => {
          await qc.invalidateQueries({ queryKey: queryKeys.accounts() });
          const cached = qc.getQueryData<unknown[]>(queryKeys.accounts());
          if (ms === 12000 && (!cached || cached.length === 0)) {
            toast.error("No TikTok accounts found. Check your token permissions and try reconnecting.");
          }
        }, ms);
      checkAfter(5000);
      checkAfter(12000);
      router.replace(pathname);
    } else if (tiktokStatus === "error") {
      toast.error("TikTok connection failed. Please try again.");
      router.replace(pathname);
    }

    const googleStatus = searchParams.get("google");
    if (googleStatus === "connected") {
      qc.invalidateQueries({ queryKey: ["connections"] });
      qc.invalidateQueries({ queryKey: queryKeys.accounts() });
      toast.success("Google Ads connected. Syncing your data…");
      setConnectSuccess(true);
      setSyncBannerPlatform({ key: "google_ads", name: "Google Ads" });
      setTimeout(() => setConnectSuccess(false), 4000);
      const checkAfter = (ms: number) =>
        setTimeout(async () => {
          await qc.invalidateQueries({ queryKey: queryKeys.accounts() });
          const cached = qc.getQueryData<unknown[]>(queryKeys.accounts());
          if (ms === 12000 && (!cached || cached.length === 0)) {
            toast.error("No Google Ads accounts found. Check your developer token / MCC access and try reconnecting.");
          }
        }, ms);
      checkAfter(5000);
      checkAfter(12000);
      router.replace(pathname);
    } else if (googleStatus === "error") {
      toast.error("Google Ads connection failed. Please try again.");
      router.replace(pathname);
    }
  }, [searchParams, qc, router, pathname]);

  const { data: connectionsRes, isLoading } = useQuery({
    queryKey: ["connections"],
    queryFn: () => connectionsApi.list(),
    staleTime: 5 * 60 * 1000,
  });
  const connections: Connection[] = connectionsRes?.data?.data ?? [];

  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } =
    useForm<TokenForm>({ resolver: zodResolver(tokenSchema) });

  const connectMutation = useMutation({
    mutationFn: ({ platform, token }: { platform: string; token: string }) =>
      connectionsApi.create(platform, token),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connections"] });
      qc.invalidateQueries({ queryKey: queryKeys.accounts() });
      toast.success("Connected. Syncing your data…");
      setConnectSuccess(true);
      reset();
      setTimeout(() => {
        setConnectingPlatform(null);
        setConnectSuccess(false);
        setSyncBannerPlatform(connectingPlatform ? { key: connectingPlatform.key, name: connectingPlatform.name } : null);
      }, 2000);
      const checkAfter = (ms: number) =>
        setTimeout(async () => {
          await qc.invalidateQueries({ queryKey: queryKeys.accounts() });
          const cached = qc.getQueryData<unknown[]>(queryKeys.accounts());
          if (ms === 12000 && (!cached || cached.length === 0)) {
            toast.error("No accounts found. Your token may be invalid or missing required permissions.");
          }
        }, ms);
      checkAfter(5000);
      checkAfter(12000);
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      const msg = typeof detail === "string" ? detail : "Connection failed. Check your token.";
      toast.error(msg);
      setConnectError(msg);
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: (id: string) => connectionsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connections"] });
      qc.invalidateQueries({ queryKey: queryKeys.accounts() });
      setDisconnectId(null);
    },
  });

  async function onConnect(values: TokenForm) {
    if (!connectingPlatform) return;
    setConnectError(null);
    await connectMutation.mutateAsync({
      platform: connectingPlatform.key,
      token:    values.access_token,
    });
  }

  async function handleOAuthConnect(platform: typeof PLATFORMS[0]) {
    setOauthLoading(true);
    setConnectError(null);
    try {
      const res = platform.key === "google_ads"
        ? await connectionsApi.initiateGoogleOAuth()
        : await connectionsApi.initiateTikTokOAuth();
      const authUrl = res.data?.data?.auth_url;
      if (authUrl) {
        window.location.href = authUrl;
      }
    } catch {
      const msg = `Could not initiate ${platform.name} OAuth. Please try again.`;
      toast.error(msg);
      setConnectError(msg);
      setOauthLoading(false);
    }
  }

  function openConnect(platform: typeof PLATFORMS[0]) {
    setConnectingPlatform(platform);
    setConnectError(null);
    setConnectSuccess(false);
    reset();
  }

  return (
    <div className="space-y-4">
      {syncBannerPlatform && (
        <SyncProgressBanner
          platformKey={syncBannerPlatform.key}
          platformName={syncBannerPlatform.name}
          onDismiss={() => setSyncBannerPlatform(null)}
        />
      )}
      {connectError && !connectingPlatform && (
        <Alert variant="destructive">
          <AlertDescription>{connectError}</AlertDescription>
        </Alert>
      )}
      {isLoading
        ? Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <div className="h-16 animate-pulse rounded bg-muted" />
              </CardContent>
            </Card>
          ))
        : PLATFORMS.map((platform) => {
            const conn = connections.find(
              (c) => c.platform === platform.key && c.is_active
            );

            return (
              <Card key={platform.key}>
                <CardHeader className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 items-start gap-3">
                      <PlatformIcon platform={platform} />
                      <div className="min-w-0">
                        <p className="font-medium">{platform.name}</p>
                        {conn ? (
                          <div className="mt-0.5 space-y-0.5 text-xs text-muted-foreground">
                            <div className="flex flex-wrap items-center gap-x-1">
                              <AnimatedIcon
                                icon={CheckCircle2}
                                motionPreset="pop"
                                trigger="state"
                                appear
                                activeVariant="show"
                                iconClassName="size-3 text-green-500"
                              />
                              <span>Connected</span>
                              {conn.token_type && <span>· {conn.token_type.replace(/_/g, " ")}</span>}
                            </div>
                            {conn.connected_by && (
                              <p>Connected by {conn.connected_by}
                                {conn.connected_at && ` · ${formatDistanceToNow(new Date(conn.connected_at), { addSuffix: true })}`}
                              </p>
                            )}
                            {conn.last_used_at && (
                              <p>Last used {formatDistanceToNow(new Date(conn.last_used_at), { addSuffix: true })}</p>
                            )}
                          </div>
                        ) : (
                          <div className="flex items-center gap-1 mt-0.5 text-xs text-muted-foreground">
                            <XCircle className="size-3" />
                            <span>Not connected</span>
                          </div>
                        )}
                      </div>
                    </div>

                    {conn ? (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={!isOwner}
                        title={!isOwner ? "Owner only" : undefined}
                        className="shrink-0 text-destructive border-destructive/30 hover:bg-destructive/5"
                        onClick={() => setDisconnectId(conn.id)}
                      >
                        Disconnect
                      </Button>
                    ) : platform.auth_type === "oauth" ? (
                      <Button
                        size="sm"
                        className="group shrink-0"
                        onClick={() => handleOAuthConnect(platform)}
                        disabled={oauthLoading || !isOwner}
                        title={!isOwner ? "Owner only" : undefined}
                      >
                        <AnimatedIcon icon={ExternalLink} motionPreset="draw" iconClassName="size-3.5" />
                        {oauthLoading ? "Redirecting…" : "Connect"}
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        className="group shrink-0"
                        disabled={!isOwner}
                        title={!isOwner ? "Owner only" : undefined}
                        onClick={() => openConnect(platform)}
                      >
                        <AnimatedIcon icon={Plug} motionPreset="draw" iconClassName="size-3.5" />
                        Connect
                      </Button>
                    )}
                  </div>
                </CardHeader>
              </Card>
            );
          })}

      {/* Connect dialog */}
      <Dialog
        open={!!connectingPlatform}
        onOpenChange={(o) => { if (!o) { setConnectingPlatform(null); reset(); } }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Connect {connectingPlatform?.name}</DialogTitle>
            <DialogDescription>
              Follow the steps below to generate an access token.
            </DialogDescription>
          </DialogHeader>
          {connectingPlatform && (
            <pre className="whitespace-pre-wrap rounded bg-muted p-3 text-xs text-foreground">
              {connectingPlatform.instructions}
            </pre>
          )}

          {connectSuccess ? (
            <Alert>
              <AlertDescription>
                <p className="font-medium text-sm">Connected successfully!</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Last 7 days ready in ~2–8 min. Historical data (14d / 30d / 90d) ready in ~3–15 min.
                </p>
              </AlertDescription>
            </Alert>
          ) : (
            <form onSubmit={handleSubmit(onConnect)} className="space-y-4">
              {connectError && (
                <Alert variant="destructive">
                  <AlertDescription>{connectError}</AlertDescription>
                </Alert>
              )}
              <div className="space-y-1.5">
                <Label htmlFor="access-token">Access token</Label>
                <Input
                  id="access-token"
                  type="password"
                  placeholder="EAABwzLixnjY..."
                  {...register("access_token")}
                />
                {errors.access_token && (
                  <p className="text-xs text-destructive">{errors.access_token.message}</p>
                )}
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setConnectingPlatform(null)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Verifying…" : "Connect"}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* Disconnect confirm dialog */}
      <Dialog open={!!disconnectId} onOpenChange={(o) => { if (!o) setDisconnectId(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Disconnect platform</DialogTitle>
            <DialogDescription>
              This will pause all syncs for this platform. Your historical data will be preserved.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDisconnectId(null)}>Cancel</Button>
            <Button
              variant="destructive"
              disabled={disconnectMutation.isPending}
              onClick={() => disconnectId && disconnectMutation.mutate(disconnectId)}
            >
              {disconnectMutation.isPending ? "Disconnecting…" : "Disconnect"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function ConnectionsSettingsPage() {
  return (
    <Suspense>
      <ConnectionsSettingsPageInner />
    </Suspense>
  );
}
