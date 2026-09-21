"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";

export default function ForgotPasswordPage() {
  const [username, setUsername] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const res = await fetch("/api/auth/request-reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username }),
      });
      if (!res.ok) {
        setError((await res.json().catch(() => ({}))).error ?? "Something went wrong.");
        return;
      }
      setSent(true);
    } catch {
      setError("Could not reach the server. Try again.");
    } finally {
      setPending(false);
    }
  }

  if (sent) {
    return (
      <div className="flex flex-col gap-4">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Check your email</h1>
          {/* Same wording whether or not the username exists — the backend
              deliberately doesn't reveal that. */}
          <p className="mt-1 text-[12.5px] text-text-muted">
            If an account exists for <strong>{username}</strong>, we&apos;ve sent a password
            reset link to the email on file. The link expires in one hour.
          </p>
        </div>
        <Link href="/login" className="text-center text-[12px] text-accent hover:underline">
          Back to sign in
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-text-primary">Forgot your password?</h1>
        {/* <p className="mt-1 text-[12.5px] text-text-muted">
          Enter your username and we&apos;ll email a reset link to the address on your account.
        </p> */}
      </div>

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

      <Button type="submit" disabled={pending} className="mt-1 w-full">
        {pending ? "Sending…" : "Send reset link"}
      </Button>

      <Link href="/login" className="text-center text-[12px] text-accent hover:underline">
        Back to sign in
      </Link>
    </form>
  );
}
