import clsx from "clsx";
import { Brain, Check, FolderOpen, Pencil, Plus, Search, ShieldQuestion, Trash2, X } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Badge, Button, EmptyState, ErrorNotice, Field, Modal, PageHeader, Panel, Spinner, inputClass } from "../components/common/ui";
import { timeAgo, titleCase } from "../lib/format";
import { ApiError, api } from "../services/api";
import { useChat } from "../stores/chatStore";
import { useToasts } from "../stores/toastStore";
import type { Memory, MemoryCategory } from "../types/api";

const CATEGORIES: MemoryCategory[] = ["project", "person", "place", "preference", "study", "date", "command", "task", "fact"];

function MemoryRow({ m, onChange, onDelete }: { m: Memory; onChange: (m: Memory) => void; onDelete: (m: Memory) => void }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(m.value);
  const save = async () => {
    try {
      onChange(await api.patch<Memory>(`/api/memories/${m.id}`, { value }));
      setEditing(false);
    } catch (err) {
      useToasts.getState().error(err, "Couldn't update the memory");
    }
  };
  const path = typeof m.attributes.path === "string" ? m.attributes.path : null;
  return (
    <li className="py-3 flex items-start gap-3 group">
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm text-ink font-medium">{m.subject}</p>
          <Badge tone="neutral">{m.category}</Badge>
          {m.source === "inferred" && <Badge tone="violet">inferred</Badge>}
          {m.sensitivity === "personal" && <Badge tone="warn">personal</Badge>}
        </div>
        {editing ? (
          <div className="flex gap-2 mt-2">
            <input className={inputClass} value={value} onChange={(e) => setValue(e.target.value)} maxLength={4000} autoFocus
              onKeyDown={(e) => e.key === "Enter" && void save()} />
            <Button size="sm" onClick={() => void save()} icon={<Check className="size-3.5" />}>Save</Button>
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
          </div>
        ) : (
          <p className="text-sm text-muted mt-0.5 break-words">{m.value}</p>
        )}
        <div className="flex flex-wrap gap-3 mt-1 text-[0.68rem] text-dim">
          {path && <span className="inline-flex items-center gap-1"><FolderOpen className="size-3" /> {path}</span>}
          {m.aliases.length > 0 && <span>also: {m.aliases.join(", ")}</span>}
          <span>used {m.use_count}×</span>
          <span>updated {timeAgo(m.updated_at)}</span>
        </div>
      </div>
      {!editing && (
        <div className="flex opacity-60 group-hover:opacity-100">
          <button onClick={() => setEditing(true)} className="p-1.5 text-dim hover:text-ink" aria-label="Edit"><Pencil className="size-3.5" /></button>
          <button onClick={() => onDelete(m)} className="p-1.5 text-dim hover:text-rose" aria-label="Delete"><Trash2 className="size-3.5" /></button>
        </div>
      )}
    </li>
  );
}

export default function MemoryPage() {
  const [items, setItems] = useState<Memory[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [category, setCategory] = useState<MemoryCategory | "all">("all");
  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const [wipe, setWipe] = useState(false);
  const [form, setForm] = useState({ category: "project" as MemoryCategory, subject: "", value: "", path: "" });
  const lastReply = useChat((s) => s.lastReply?.at);

  const load = useCallback(async () => {
    try {
      setItems(await api.get<Memory[]>("/api/memories"));
      setError(null);
      useChat.setState({ memorySuggestions: 0 });
    } catch (err) {
      setError(ApiError.from(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, lastReply]);

  const pending = useMemo(() => (items ?? []).filter((m) => m.status === "pending"), [items]);
  const active = useMemo(() => (items ?? []).filter((m) =>
    m.status === "active" && (category === "all" || m.category === category) &&
    (!query || `${m.subject} ${m.value} ${m.aliases.join(" ")}`.toLowerCase().includes(query.toLowerCase()))), [items, category, query]);

  const replace = (m: Memory) => setItems((list) => list?.map((x) => (x.id === m.id ? m : x)) ?? null);
  const del = async (m: Memory) => {
    try {
      await api.del(`/api/memories/${m.id}`);
      setItems((list) => list?.filter((x) => x.id !== m.id) ?? null);
    } catch (err) {
      useToasts.getState().error(err, "Couldn't delete the memory");
    }
  };
  const approve = async (m: Memory) => {
    try {
      replace(await api.post<Memory>(`/api/memories/${m.id}/approve`));
    } catch (err) {
      useToasts.getState().error(err);
    }
  };
  const create = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const attributes = form.path.trim() ? { path: form.path.trim() } : {};
      const m = await api.post<Memory>("/api/memories", { category: form.category, subject: form.subject, value: form.value, attributes });
      setItems((list) => [m, ...(list ?? [])]);
      setAdding(false);
      setForm({ category: "project", subject: "", value: "", path: "" });
    } catch (err) {
      useToasts.getState().error(err, "Couldn't save the memory");
    }
  };
  const wipeAll = async () => {
    try {
      await api.del("/api/memories?confirm=true");
      setItems([]);
      setWipe(false);
      useToasts.getState().push({ kind: "success", title: "All memories deleted" });
    } catch (err) {
      useToasts.getState().error(err);
    }
  };

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto">
      <PageHeader
        title="Memory"
        subtitle="What NEXUS remembers about you. Secrets are never stored; inferred and personal facts wait for your approval."
        actions={
          <>
            <Button variant="danger" size="sm" onClick={() => setWipe(true)} disabled={!items?.length}>Delete all</Button>
            <Button variant="primary" size="sm" icon={<Plus className="size-3.5" />} onClick={() => setAdding(true)}>Add memory</Button>
          </>
        }
      />
      {error && <ErrorNotice title={error.message} reason={error.reason} nextStep={error.nextStep} onRetry={load} />}
      {pending.length > 0 && (
        <Panel title={`Awaiting approval (${pending.length})`} icon={<ShieldQuestion className="size-3.5" />} className="mb-4 border-amber/25">
          <ul className="divide-y divide-line">
            {pending.map((m) => (
              <li key={m.id} className="py-2.5 flex items-center gap-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm"><span className="text-ink font-medium">{m.subject}</span> <span className="text-muted">— {m.value}</span></p>
                  <p className="text-[0.68rem] text-dim">{m.source === "inferred" ? "NEXUS noticed this in conversation" : "Personal information"}</p>
                </div>
                <Button size="sm" onClick={() => void approve(m)} icon={<Check className="size-3.5" />}>Remember</Button>
                <Button size="sm" variant="ghost" onClick={() => void del(m)} icon={<X className="size-3.5" />}>Discard</Button>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      <Panel title="Long-term memory" icon={<Brain className="size-3.5" />}>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <div className="relative flex-1 min-w-48">
            <Search className="size-3.5 text-dim absolute left-3 top-1/2 -translate-y-1/2" />
            <input className={clsx(inputClass, "pl-8")} placeholder="Search memories" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <div className="flex flex-wrap gap-1">
            {(["all", ...CATEGORIES] as const).map((c) => (
              <button key={c} onClick={() => setCategory(c)}
                className={clsx("text-xs px-2.5 py-1 rounded-lg", category === c ? "bg-cyan/15 text-cyan" : "text-muted hover:text-ink")}>
                {titleCase(c)}
              </button>
            ))}
          </div>
        </div>
        {items === null && !error ? <Spinner /> : active.length === 0 ? (
          <EmptyState icon={<Brain className="size-6" />} title="Nothing here yet">
            Tell NEXUS things like “My college AI project is LinkGuard AI” or “Remember that ~/college contains my college projects”.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-line">
            {active.map((m) => <MemoryRow key={m.id} m={m} onChange={replace} onDelete={(x) => void del(x)} />)}
          </ul>
        )}
      </Panel>

      <Modal open={adding} onClose={() => setAdding(false)} title="Add a memory"
        footer={<><Button variant="ghost" onClick={() => setAdding(false)}>Cancel</Button>
          <Button variant="primary" type="submit" form="memory-form">Save</Button></>}>
        <form id="memory-form" onSubmit={create} className="space-y-3">
          <Field label="Category">
            <select className={inputClass} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value as MemoryCategory })}>
              {CATEGORIES.map((c) => <option key={c} value={c}>{titleCase(c)}</option>)}
            </select>
          </Field>
          <Field label="Subject" hint="How you'll refer to it, e.g. “college AI project”.">
            <input className={inputClass} required minLength={2} maxLength={200} value={form.subject}
              onChange={(e) => setForm({ ...form, subject: e.target.value })} />
          </Field>
          <Field label="Value">
            <input className={inputClass} required maxLength={4000} value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} />
          </Field>
          <Field label="Folder path (optional)" hint="Lets NEXUS open this project or folder for you.">
            <input className={inputClass} value={form.path} onChange={(e) => setForm({ ...form, path: e.target.value })} placeholder="~/projects/linkguard" />
          </Field>
        </form>
      </Modal>

      <Modal open={wipe} onClose={() => setWipe(false)} title="Delete all memories?" tone="danger"
        footer={<><Button variant="ghost" onClick={() => setWipe(false)}>Cancel</Button>
          <Button variant="danger" onClick={() => void wipeAll()}>Delete everything</Button></>}>
        <p className="text-sm text-muted">This permanently removes all {items?.length ?? 0} memories. Conversations and files are not affected.</p>
      </Modal>
    </div>
  );
}
