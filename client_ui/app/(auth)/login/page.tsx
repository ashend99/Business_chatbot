"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, Input, PasswordInput } from "@/components/ui/Field";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [resetDone, setResetDone] = useState(false);

  // Set by /reset-password after a successful reset. Read in an effect (not
  // useSearchParams) to avoid needing a Suspense boundary around the form.
  useEffect(() => {
    setResetDone(new URLSearchParams(window.location.search).get("reset") === "1");
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.error ?? "Login failed.");
        return;
      }
      const next = new URLSearchParams(window.location.search).get("next") || "/";
      router.replace(next.startsWith("/") ? next : "/");
      router.refresh();
    } catch {
      setError("Could not reach the server. Try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-text-primary">Sign in</h1>
        <p className="mt-1 text-[12.5px] text-text-muted">
          Use the credentials you set when activating your account.
        </p>
      </div>

      {resetDone && !error && (
        <p className="rounded-lg bg-green-50 px-3 py-2 text-[12.5px] text-green-700 dark:bg-green-950/40 dark:text-green-400">
          Password updated. Sign in with your new password.
        </p>
      )}

      {error && (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-[12.5px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
          {error}
        </p>
      )}

      <Field label="Username">
        <Input
          autoFocus
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
      </Field>
      <Field label="Password">
        <PasswordInput
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </Field>

      <Button type="submit" disabled={pending} className="mt-1 w-full">
        {pending ? "Signing in…" : "Sign in"}
      </Button>

      <p className="text-center">
        <Link
          href="/forgot-password"
          className="text-[13px] font-medium text-accent-soft-fg underline underline-offset-2 hover:opacity-80"
        >
          Forgot your password?
        </Link>
      </p>
    </form>
  );
}
