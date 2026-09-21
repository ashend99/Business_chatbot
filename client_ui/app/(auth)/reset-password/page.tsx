"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, PasswordInput } from "@/components/ui/Field";

function ResetFlow() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  if (!token) {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-lg font-semibold text-text-primary">Missing link</h1>
        <p className="text-[12.5px] text-text-muted">
          Open the reset link from your email — it carries the token this page needs.
        </p>
        <Link href="/forgot-password" className="text-[12px] text-accent hover:underline">
          Request a new link
        </Link>
      </div>
    );
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setPending(true);
    try {
      const res = await fetch("/api/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
      });
      if (!res.ok) {
        setError((await res.json().catch(() => ({}))).error ?? "Could not reset your password.");
        return;
      }
      // The user still has to sign in with the new password — no auto-login,
      // since the reset link came from email, not an authenticated session.
      router.replace("/login?reset=1");
    } catch {
      setError("Could not reach the server. Try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-text-primary">Choose a new password</h1>
        <p className="mt-1 text-[12.5px] text-text-muted">At least 8 characters.</p>
      </div>

      {error && (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-[12.5px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
          {error}
        </p>
      )}

      <Field label="New password">
        <PasswordInput
          autoFocus
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          minLength={8}
          required
        />
      </Field>
      <Field label="Confirm new password">
        <PasswordInput
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          required
        />
      </Field>

      <Button type="submit" disabled={pending} className="mt-1 w-full">
        {pending ? "Saving…" : "Reset password"}
      </Button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={<h1 className="text-lg font-semibold text-text-primary">Reset password</h1>}
    >
      <ResetFlow />
    </Suspense>
  );
}
