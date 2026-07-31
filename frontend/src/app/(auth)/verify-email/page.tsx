"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { authApi } from "@/lib/api/auth";
import { setAuthCookie } from "@/lib/api/client";

type State = "loading" | "success" | "error";

function VerifyEmailContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [state, setState] = useState<State>("loading");
  const [errorMsg, setErrorMsg] = useState<string>("This link has expired or is invalid.");

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
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-bold tracking-tight">DashMet</h1>
        </div>

        <Card>
          {state === "loading" && (
            <>
              <CardHeader>
                <CardTitle>Verifying your email…</CardTitle>
                <CardDescription>This will only take a moment.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex justify-center py-4">
                  <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                </div>
              </CardContent>
            </>
          )}

          {state === "success" && (
            <>
              <CardHeader>
                <CardTitle>Email verified!</CardTitle>
                <CardDescription>
                  Logging you in…
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex justify-center py-4">
                  <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                </div>
              </CardContent>
            </>
          )}

          {state === "error" && (
            <>
              <CardHeader>
                <CardTitle>Verification failed</CardTitle>
                <CardDescription>{errorMsg}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <Link href="/login">
                  <Button className="w-full">Back to sign in</Button>
                </Link>
              </CardContent>
            </>
          )}
        </Card>
      </div>
    </div>
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
