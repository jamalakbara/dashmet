"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { orgApi } from "@/lib/api/org";
import { queryKeys } from "@/lib/query-keys";
import { useIsOwner } from "@/hooks/use-role";

const schema = z.object({ name: z.string().min(1, "Required") });
type FormValues = z.infer<typeof schema>;

export default function OrgSettingsPage() {
  const qc = useQueryClient();
  const isOwner = useIsOwner();
  const [saved, setSaved] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  const { data: orgRes, isLoading } = useQuery({
    queryKey: ["org"],
    queryFn: () => orgApi.get(),
    staleTime: 30 * 60 * 1000,
  });

  const org = orgRes?.data?.data as { id: string; name: string; slug: string } | undefined;

  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } =
    useForm<FormValues>({ resolver: zodResolver(schema) });

  useEffect(() => {
    if (org) reset({ name: org.name });
  }, [org, reset]);

  const updateMutation = useMutation({
    mutationFn: (name: string) => orgApi.update(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["org"] });
      qc.invalidateQueries({ queryKey: queryKeys.me() });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setApiError(typeof detail === "string" ? detail : "Failed to save");
    },
  });

  async function onSubmit(values: FormValues) {
    setApiError(null);
    await updateMutation.mutateAsync(values.name);
  }

  return (
    <div className="space-y-8">
      {/* Org name */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Organization</CardTitle>
          <CardDescription>Update your organization&apos;s display name.</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              <div className="h-4 w-24 animate-pulse rounded bg-muted" />
              <div className="h-8 w-80 animate-pulse rounded bg-muted" />
            </div>
          ) : (
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 max-w-sm">
              {apiError && (
                <Alert variant="destructive">
                  <AlertDescription>{apiError}</AlertDescription>
                </Alert>
              )}
              {saved && (
                <Alert>
                  <AlertDescription>Changes saved.</AlertDescription>
                </Alert>
              )}
              <div className="space-y-1.5">
                <Label htmlFor="org-name">Name</Label>
                <Input id="org-name" {...register("name")} />
                {errors.name && (
                  <p className="text-xs text-destructive">{errors.name.message}</p>
                )}
              </div>
              <div className="space-y-1.5">
                <Label className="text-muted-foreground">Slug</Label>
                <Input value={org?.slug ?? ""} readOnly disabled className="font-mono text-xs" />
              </div>
              <Button
                type="submit"
                disabled={isSubmitting || !isOwner}
                title={!isOwner ? "Owner only" : undefined}
              >
                {isSubmitting ? "Saving…" : "Save changes"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
