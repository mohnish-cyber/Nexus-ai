import { useEffect, useRef } from "react";
import { useShallow } from "zustand/react/shallow";
import { currentMessages, liveForCurrent, useChat } from "../../stores/chatStore";
import { LiveResponse } from "./LiveResponse";
import { MessageBubble } from "./MessageBubble";

export function ChatThread({ empty, limit }: { empty?: React.ReactNode; limit?: number }) {
  const messages = useChat(useShallow(currentMessages));
  const live = useChat(useShallow(liveForCurrent));
  const endRef = useRef<HTMLDivElement>(null);
  const shown = limit ? messages.slice(-limit) : messages;
  const liveText = live.map((l) => l.segments.map((s) => s.text).join("").length).join(",");

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [shown.length, live.length, liveText]);

  if (shown.length === 0 && live.length === 0) return <>{empty}</>;
  return (
    <div className="space-y-5">
      {limit && messages.length > limit && (
        <p className="text-center text-[0.7rem] text-dim">Showing the latest {limit} messages · full history in Assistant</p>
      )}
      {shown.map((m) => <MessageBubble key={m.id} message={m} />)}
      {live.map((l) => <LiveResponse key={l.requestId} live={l} />)}
      <div ref={endRef} />
    </div>
  );
}
