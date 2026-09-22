"use client";

import { useEffect, useRef, useState } from "react";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

type BotAction = { type: string; lead_id: string | null };

const STORAGE_KEY = "widget-test-external-user-id";

function getOrCreateUserId(): string {
  let id = localStorage.getItem(STORAGE_KEY);
  if (!id) {
    id = `visitor-${crypto.randomUUID()}`;
    localStorage.setItem(STORAGE_KEY, id);
  }
  return id;
}

export function ChatWidget() {
  const [userId, setUserId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastActions, setLastActions] = useState<BotAction[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // localStorage is unavailable during SSR, so the id can only be read
  // client-side -- server markup renders the "…" placeholder until this
  // fires once on mount.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setUserId(getOrCreateUserId());
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  function newConversation() {
    const id = `visitor-${crypto.randomUUID()}`;
    localStorage.setItem(STORAGE_KEY, id);
    setUserId(id);
    setMessages([]);
    setLastActions([]);
    setError(null);
  }

  async function send() {
    const text = input.trim();
    if (!text || !userId || sending) return;
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setSending(true);
    setError(null);
    try {
      const res = await fetch("/api/bot/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel_type: "website_widget", external_user_id: userId, text }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Bot request failed.");
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
      setLastActions(data.actions ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setSending(false);
    }
  }

  return (
    // The widget is always light (hard-coded white surfaces), so it sets its own
    // text color -- otherwise it inherits the dashboard's light-on-dark text
    // color when the dark theme is active, giving white text on white.
    <div className="flex h-[560px] flex-col overflow-hidden rounded-2xl border border-neutral-200 bg-white text-neutral-900 shadow-lg">
      <div className="flex items-center justify-between border-b border-neutral-200 px-4 py-3">
        <div>
          <p className="text-[13px] font-semibold text-neutral-800">Dula&apos;s Kitchen</p>
          <p className="truncate text-[10.5px] text-neutral-400">{userId ?? "…"}</p>
        </div>
        <button
          type="button"
          onClick={newConversation}
          className="rounded-lg border border-neutral-200 px-2.5 py-1 text-[11px] text-neutral-600 hover:bg-neutral-50"
        >
          New conversation
        </button>
      </div>

      <div ref={scrollRef} className="flex flex-1 flex-col gap-2 overflow-y-auto p-4">
        {messages.length === 0 && (
          <p className="mt-6 text-center text-[12.5px] text-neutral-400">
            Say hi to test the bot — try asking about menu prices, hours, or delivery.
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[80%] whitespace-pre-wrap rounded-xl px-3 py-2 text-[13px] ${
              m.role === "user"
                ? "self-end rounded-br-sm bg-neutral-800 text-white"
                : "self-start rounded-bl-sm bg-neutral-100 text-neutral-900"
            }`}
          >
            {m.content}
          </div>
        ))}
        {sending && <div className="self-start text-[12px] text-neutral-400">Typing…</div>}
      </div>

      {lastActions.length > 0 && (
        <div className="border-t border-neutral-100 bg-amber-50 px-4 py-1.5 text-[11px] text-amber-700">
          Action: {lastActions.map((a) => a.type).join(", ")}
        </div>
      )}
      {error && (
        <div className="border-t border-neutral-100 bg-red-50 px-4 py-1.5 text-[11px] text-red-700">{error}</div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="flex items-center gap-2 border-t border-neutral-200 p-3"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a message…"
          disabled={!userId || sending}
          className="flex-1 rounded-lg border border-neutral-200 bg-white px-3 py-2 text-[13px] text-neutral-900 outline-none placeholder:text-neutral-400 focus:border-neutral-400"
        />
        <button
          type="submit"
          disabled={!userId || sending || !input.trim()}
          className="rounded-lg bg-neutral-800 px-3.5 py-2 text-[13px] font-medium text-white disabled:opacity-40"
        >
          Send
        </button>
      </form>
    </div>
  );
}
