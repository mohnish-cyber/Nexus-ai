import { Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { ActivityPanel } from "../components/activity/ActivityPanel";
import { ChatComposer } from "../components/chat/ChatComposer";
import { ChatThread } from "../components/chat/ChatThread";
import { NexusOrb, ORB_STATE_TEXT } from "../components/orb/NexusOrb";
import { TelemetryPanel } from "../components/system/TelemetryPanel";
import { TodayPanel } from "../components/system/TodayPanel";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { greeting } from "../lib/format";
import { useChat } from "../stores/chatStore";
import { useSettings } from "../stores/settingsStore";
import { useSystem } from "../stores/systemStore";
import { useVoice } from "../stores/voiceStore";

const SUGGESTIONS = [
  "What tasks do I have today?",
  "What's the weather tomorrow?",
  "What do you remember about me?",
  "Search the latest AI news",
];

export default function HomePage() {
  const orb = useSystem((s) => s.orb);
  const orbLabel = useSystem((s) => s.orbLabel);
  const level = useSystem((s) => s.audioLevel);
  const ai = useSystem((s) => s.status?.components.ai);
  const toggleVoice = useVoice((s) => s.toggle);
  const send = useChat((s) => s.send);
  const hasMessages = useChat((s) => (s.messages[s.currentId ?? "__new__"] ?? []).length > 0 || Object.keys(s.live).length > 0);
  const name = useSettings((s) => s.bundle?.preferences.profile.user_name);
  const wide = useMediaQuery("(min-width: 1024px)");
  const orbSize = hasMessages ? (wide ? 170 : 120) : wide ? 290 : 200;

  return (
    <div className="h-full grid gap-4 p-3 sm:p-4 xl:grid-cols-[17rem_minmax(0,1fr)_19rem] lg:grid-cols-[minmax(0,1fr)_18rem]">
      <div className="hidden xl:flex flex-col gap-4 min-h-0">
        <TodayPanel />
      </div>

      <section className="flex flex-col h-[calc(100dvh-9.5rem)] min-h-[28rem] lg:h-auto lg:min-h-0" aria-label="Assistant">
        <div className={`flex flex-col items-center shrink-0 transition-all duration-500 ${hasMessages ? "pt-1" : "pt-2 sm:pt-10"}`}>
          <NexusOrb
            state={orb}
            level={level}
            size={orbSize}
            onClick={() => void toggleVoice()}
            ariaLabel="Talk to NEXUS (push to talk)"
          />
          <p className="mt-1 text-sm font-medium tracking-wide text-ink/90" aria-live="polite">
            {orbLabel ?? ORB_STATE_TEXT[orb]}
          </p>
          {!hasMessages && (
            <p className="mt-2 text-xs text-muted text-center max-w-sm">
              {greeting()}{name ? `, ${name}` : ""}. Tap the orb to speak
              {wide && <> or press <kbd className="font-mono text-cyan/80">Ctrl+Shift+Space</kbd></>}.
            </p>
          )}
          {ai && !ai.ready && (
            <Link to="/settings" className="mt-3 inline-flex items-center gap-1.5 text-xs text-amber border border-amber/30 bg-amber/5 rounded-lg px-3 py-1.5 hover:bg-amber/10">
              <Sparkles className="size-3.5" />
              {ai.configured ? "AI core unreachable — check Settings" : "Limited mode — connect the AI core in Settings"}
            </Link>
          )}
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin px-1 sm:px-4 py-4">
          <div className="max-w-3xl mx-auto">
            <ChatThread
              limit={8}
              empty={
                <div className="flex flex-wrap justify-center gap-2 pt-2">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} onClick={() => send(s)}
                      className="text-xs text-muted border border-line rounded-full px-3 py-1.5 hover:text-ink hover:border-cyan/40 hover:bg-cyan/5 transition">
                      {s}
                    </button>
                  ))}
                </div>
              }
            />
          </div>
        </div>
        <div className="shrink-0 max-w-3xl w-full mx-auto">
          <ChatComposer placeholder={wide ? "Ask, command or delegate…" : "Ask or command NEXUS…"} />
        </div>
      </section>

      <div className="flex flex-col gap-4 min-h-0">
        <ActivityPanel className="flex-1 min-h-[16rem] max-h-[50vh] lg:max-h-none" />
        <TelemetryPanel />
        <div className="xl:hidden"><TodayPanel /></div>
      </div>
    </div>
  );
}
