"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, Input, PasswordInput } from "@/components/ui/Field";

function ActivateFlow() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const tokenEmail = params.get("email") ?? "";

  const [step, setStep] = useState<1 | 2>(1);
  const [email, setEmail] = useState(tokenEmail);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  if (!token) {
    return (
      <div className="flex flex-col gap-2">
        <h1 className="text-lg font-semibold text-text-primary">Missing link</h1>
        <p className="text-[12.5px] text-text-muted">
          Open the activation link from your invitation email — it carries the
          token this page needs.
        </p>
      </div>
    );
  }

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const res = await fetch("/api/auth/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, email }),
      });
      if (!res.ok) {
        setError((await res.json().catch(() => ({}))).error ?? "Verification failed.");
        return;
      }
      setStep(2);
    } catch {
      setError("Could not reach the server. Try again.");
    } finally {
      setPending(false);
    }
  }

  async function complete(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setPending(true);
    try {
      const res = await fetch("/api/auth/activate/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, username, password }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.error ?? "Could not create your account.");
        return;
      }
      if (body.login) {
        router.replace("/");
        router.refresh();
      } else {
        router.replace("/login");
      }
    } catch {
      setError("Could not reach the server. Try again.");
    } finally {
      setPending(false);
    }
  }

  return step === 1 ? (
    <form onSubmit={verify} className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-text-primary">Activate your account</h1>
        <p className="mt-1 text-[12.5px] text-text-muted">
          Confirm the email this invitation was sent to.
        </p>
      </div>
      {error && (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-[12.5px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
          {error}
        </p>
      )}
      <Field label="Email">
        <Input
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </Field>
      <Button type="submit" disabled={pending} className="mt-1 w-full">
        {pending ? "Checking…" : "Continue"}
      </Button>
    </form>
  ) : (
    <form onSubmit={complete} className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-text-primary">Choose your login</h1>
        <p className="mt-1 text-[12.5px] text-text-muted">
          You&apos;ll use these to sign in from now on.
        </p>
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
      <Field label="Password">
        <PasswordInput
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          minLength={8}
          required
        />
      </Field>
      <Field label="Confirm password">
        <PasswordInput
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          required
        />
      </Field>
      <Button type="submit" disabled={pending} className="mt-1 w-full">
        {pending ? "Creating…" : "Create account"}
      </Button>
    </form>
  );
}

export default function ActivatePage() {
  return (
    <Suspense
      fallback={
        <h1 className="text-lg font-semibold text-text-primary">Activate your account</h1>
      }
    >
      <ActivateFlow />
    </Suspense>
  );
}
