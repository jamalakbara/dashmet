"use client";

import { Suspense, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { formatDistanceToNow } from "date-fns";
import { CheckCircle2, XCircle, Plug, ExternalLink } from "lucide-react";
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
import { queryKeys } from "@/lib/query-keys";

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
    auth_type: "soon" as const,
    instructions: undefined,
  },
];

function PlatformIcon({ platform }: { platform: typeof PLATFORMS[0] }) {
  return (
    <div className={`flex size-10 shrink-0 items-center justify-center rounded-lg ${platform.color} text-sm font-bold text-white`}>
      {platform.icon}
    </div>
  );
}

function ConnectionsSettingsPageInner() {
  const qc = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [connectingPlatform, setConnectingPlatform] = useState<typeof PLATFORMS[0] | null>(null);
  const [disconnectId, setDisconnectId] = useState<string | null>(null);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [connectSuccess, setConnectSuccess] = useState(false);
  const [oauthLoading, setOauthLoading] = useState(false);

  // Handle return from TikTok OAuth callback
  useEffect(() => {
    const tiktokStatus = searchParams.get("tiktok");
    if (tiktokStatus === "connected") {
      qc.invalidateQueries({ queryKey: ["connections"] });
      qc.invalidateQueries({ queryKey: queryKeys.accounts() });
      setConnectSuccess(true);
      setTimeout(() => setConnectSuccess(false), 4000);
      router.replace(pathname);
    } else if (tiktokStatus === "error") {
      setConnectError("TikTok connection failed. Please try again.");
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
      setConnectSuccess(true);
      reset();
      setTimeout(() => {
        setConnectingPlatform(null);
        setConnectSuccess(false);
      }, 2000);
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setConnectError(typeof detail === "string" ? detail : "Connection failed. Check your token.");
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: (id: string) => connectionsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connections"] });
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
      const res = await connectionsApi.initiateTikTokOAuth();
      const authUrl = res.data?.data?.auth_url;
      if (authUrl) {
        window.location.href = authUrl;
      }
    } catch {
      setConnectError("Could not initiate TikTok OAuth. Please try again.");
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
      {connectSuccess && !connectingPlatform && (
        <Alert>
          <AlertDescription>
            Platform connected successfully. Ad accounts are being imported…
          </AlertDescription>
        </Alert>
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
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <PlatformIcon platform={platform} />
                      <div>
                        <p className="font-medium">{platform.name}</p>
                        {conn ? (
                          <div className="mt-0.5 space-y-0.5 text-xs text-muted-foreground">
                            <div className="flex items-center gap-1">
                              <CheckCircle2 className="size-3 text-green-500" />
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
                        className="text-destructive border-destructive/30 hover:bg-destructive/5"
                        onClick={() => setDisconnectId(conn.id)}
                      >
                        Disconnect
                      </Button>
                    ) : platform.auth_type === "soon" ? (
                      <Button size="sm" disabled>
                        Coming soon
                      </Button>
                    ) : platform.auth_type === "oauth" ? (
                      <Button
                        size="sm"
                        onClick={() => handleOAuthConnect(platform)}
                        disabled={oauthLoading}
                      >
                        <ExternalLink className="size-3.5" />
                        {oauthLoading ? "Redirecting…" : "Connect"}
                      </Button>
                    ) : (
                      <Button size="sm" onClick={() => openConnect(platform)}>
                        <Plug className="size-3.5" />
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
                Connection verified. Ad accounts are being imported…
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
