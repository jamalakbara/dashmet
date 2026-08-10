"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { authApi } from "@/lib/api/auth";
import { setAuthCookie } from "@/lib/api/client";

type State = "loading" | "success" | "error";

function VerifyEmailContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [state, setState] = useState<State>("loading");
  const [errorMsg, setErrorMsg] = useState<string>(
    "This link has expired or is invalid."
  );

  useEffect(() => {
    if (!token) {
      setState("error");
      return;
    }

    authApi
      .verifyEmail(token)
      .then((res) => {
        const { access_token, expires_in } = res.data.data;
        setAuthCookie(access_token, expires_in);
        setState("success");
        setTimeout(() => router.push("/dashboard"), 1500);
      })
      .catch((err) => {
        const detail = err?.response?.data?.detail;
        if (typeof detail === "string") setErrorMsg(detail);
        setState("error");
      });
  }, [token, router]);

  return (
    <AuthShell>
      {state === "loading" && (
        <>
          <div className="space-y-1.5">
            <h1 className="text-2xl font-bold tracking-tight">
              Verifying your email…
            </h1>
            <p className="text-sm text-muted-foreground">
              This will only take a moment.
            </p>
          </div>
          <div className="flex justify-center py-4">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        </>
      )}

      {state === "success" && (
        <>
          <div className="space-y-1.5">
            <h1 className="text-2xl font-bold tracking-tight">Email verified!</h1>
            <p className="text-sm text-muted-foreground">Logging you in…</p>
          </div>
          <div className="flex justify-center py-4">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        </>
      )}

      {state === "error" && (
        <>
          <div className="space-y-1.5">
            <h1 className="text-2xl font-bold tracking-tight">
              Verification failed
            </h1>
            <p className="text-sm text-muted-foreground">{errorMsg}</p>
          </div>
          <Link href="/login">
            <Button size="lg" className="w-full">
              Back to sign in
            </Button>
          </Link>
        </>
      )}
    </AuthShell>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      }
    >
      <VerifyEmailContent />
    </Suspense>
  );
}
