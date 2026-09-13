import { ChatWidget } from "@/components/widget-test/ChatWidget";

export const metadata = { title: "Bot widget test" };

export default function WidgetTestPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-neutral-100 p-6">
      <div className="flex w-full max-w-md flex-col gap-3">
        <div className="text-center">
          <h1 className="text-lg font-semibold text-neutral-800">Chat widget test harness</h1>
          <p className="text-[12.5px] text-neutral-500">
            Simulates the website_widget channel talking to POST /bot/message.
          </p>
        </div>
        <ChatWidget />
      </div>
    </div>
  );
}
