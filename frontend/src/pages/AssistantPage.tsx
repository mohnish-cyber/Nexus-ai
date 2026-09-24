import clsx from "clsx";
import { Check, MessageSquarePlus, Pencil, Search, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { ChatComposer } from "../components/chat/ChatComposer";
import { ChatThread } from "../components/chat/ChatThread";
import { EmptyState, inputClass } from "../components/common/ui";
import { NexusOrb, ORB_STATE_TEXT } from "../components/orb/NexusOrb";
import { timeAgo } from "../lib/format";
import { useChat } from "../stores/chatStore";
import { useSystem } from "../stores/systemStore";
import { useToasts } from "../stores/toastStore";
import type { FileInfo } from "../types/api";

export default function AssistantPage() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const attach = (location.state as { attach?: FileInfo[] } | null)?.attach;
  const { conversations, currentId, openConversation, newConversation, rename, remove } = useChat();
  const orb = useSystem((s) => s.orb);
  const orbLabel = useSystem((s) => s.orbLabel);
  const level = useSystem((s) => s.audioLevel);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [title, setTitle] = useState("");

  useEffect(() => {
    if (conversationId && conversationId !== currentId) void openConversation(conversationId);
  }, [conversationId, currentId, openConversation]);

  useEffect(() => {
    if (currentId && !conversationId) navigate(`/assistant/${currentId}`, { replace: true, state: location.state });
  }, [currentId, conversationId, navigate, location.state]);

  useEffect(() => {
    if (attach?.length) newConversation();
  }, [attach, newConversation]);

  const filtered = useMemo(
    () => conversations.filter((c) => c.title.toLowerCase().includes(query.toLowerCase())),
    [conversations, query],
  );
  const current = conversations.find((c) => c.id === currentId);

  const saveTitle = async (id: string) => {
    try {
      await rename(id, title.trim() || "Untitled");
    } catch (err) {
      useToasts.getState().error(err, "Couldn't rename");
    }
    setEditing(null);
  };

  const del = async (id: string) => {
    if (!window.confirm("Delete this conversation and its messages?")) return;
    try {
      await remove(id);
      if (id === currentId) navigate("/assistant");
    } catch (err) {
      useToasts.getState().error(err, "Couldn't delete the conversation");
    }
  };

  return (
    <div className="h-full flex">
      <aside className="hidden md:flex w-72 shrink-0 flex-col border-r border-line bg-deep/30">
        <div className="p-3 space-y-2">
          <button
            onClick={() => {
              newConversation();
              navigate("/assistant");
            }}
            className="w-full flex items-center justify-center gap-2 rounded-xl border border-cyan/30 bg-cyan/10 text-cyan py-2 text-sm hover:bg-cyan/15"
          >
            <MessageSquarePlus className="size-4" /> New conversation
          </button>
          <div className="relative">
            <Search className="size-3.5 text-dim absolute left-3 top-1/2 -translate-y-1/2" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search conversations"
              className={clsx(inputClass, "pl-8 py-1.5 text-xs")} aria-label="Search conversations" />
          </div>
        </div>
        <ul className="flex-1 overflow-y-auto scrollbar-thin px-2 pb-3 space-y-0.5">
          {filtered.length === 0 && <li className="text-xs text-dim text-center py-6">No conversations yet.</li>}
          {filtered.map((c) => (
            <li key={c.id} className={clsx("group rounded-lg", c.id === currentId ? "bg-cyan/10" : "hover:bg-white/[0.04]")}>
              {editing === c.id ? (
                <div className="flex items-center gap-1 p-1.5">
                  <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200}
                    onKeyDown={(e) => e.key === "Enter" && void saveTitle(c.id)} className={clsx(inputClass, "py-1 text-xs")} />
                  <button onClick={() => void saveTitle(c.id)} className="p-1 text-ok" aria-label="Save title"><Check className="size-3.5" /></button>
                  <button onClick={() => setEditing(null)} className="p-1 text-dim" aria-label="Cancel"><X className="size-3.5" /></button>
                </div>
              ) : (
                <div className="flex items-center">
                  <button onClick={() => navigate(`/assistant/${c.id}`)} className="flex-1 min-w-0 text-left px-3 py-2">
                    <p className="text-sm text-ink/90 truncate">{c.title}</p>
                    <p className="text-[0.62rem] text-dim">{timeAgo(c.updated_at)}</p>
                  </button>
                  <div className="hidden group-hover:flex pr-1.5">
                    <button onClick={() => { setEditing(c.id); setTitle(c.title); }} className="p-1 text-dim hover:text-ink"
                      aria-label="Rename"><Pencil className="size-3.5" /></button>
                    <button onClick={() => void del(c.id)} className="p-1 text-dim hover:text-rose" aria-label="Delete">
                      <Trash2 className="size-3.5" /></button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      </aside>

      <section className="flex-1 min-w-0 flex flex-col">
        <div className="shrink-0 flex items-center gap-3 px-4 py-2.5 border-b border-line">
          <NexusOrb state={orb} level={level} size={40} />
          <div className="min-w-0">
            <p className="text-sm font-medium truncate">{current?.title ?? "New conversation"}</p>
            <p className="text-[0.68rem] text-muted">{orbLabel ?? ORB_STATE_TEXT[orb]}</p>
          </div>
          <button onClick={() => { newConversation(); navigate("/assistant"); }}
            className="md:hidden ml-auto p-2 text-muted" aria-label="New conversation">
            <MessageSquarePlus className="size-5" />
          </button>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin px-3 sm:px-6 py-5">
          <div className="max-w-3xl mx-auto">
            <ChatThread
              empty={
                <EmptyState icon={<NexusOrb state="idle" size={120} />} title="How can I help?">
                  Ask a question, attach a PDF and say “explain Unit 3”, share a screenshot of an error, or give a command
                  like “remind me tomorrow at 8 AM to submit my assignment”.
                </EmptyState>
              }
            />
          </div>
        </div>
        <div className="shrink-0 px-3 sm:px-6 pb-3 sm:pb-4">
          <div className="max-w-3xl mx-auto">
            <ChatComposer key={attach?.map((a) => a.id).join(",") ?? "composer"} autoFocus initialAttachments={attach} />
          </div>
        </div>
      </section>
    </div>
  );
}
