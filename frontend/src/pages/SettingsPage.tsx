import clsx from "clsx";
import {
  AppWindow, Brain, Cpu, Database, Download, FolderLock, KeyRound, MapPin, Mic, Plus, ShieldCheck, Trash2, User,
} from "lucide-react";
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { Badge, Button, ErrorNotice, Field, Modal, PageHeader, Panel, Spinner, StatusDot, Toggle, inputClass } from "../components/common/ui";
import { timeAgo } from "../lib/format";
import { ApiError, api } from "../services/api";
import { browserVoices, speak } from "../services/voice/speech";
import { WakeWordListener } from "../services/voice/wakeword";
import { useSettings } from "../stores/settingsStore";
import { useSystem } from "../stores/systemStore";
import { useToasts } from "../stores/toastStore";
import { useVoice } from "../stores/voiceStore";
import type { AppInfo, PermissionGrant, Preferences, SecretStatus } from "../types/api";

const SECTIONS = [
  { id: "ai", label: "AI core", icon: Cpu },
  { id: "keys", label: "API keys", icon: KeyRound },
  { id: "voice", label: "Voice", icon: Mic },
  { id: "permissions", label: "Permissions", icon: ShieldCheck },
  { id: "workspace", label: "Workspace & apps", icon: FolderLock },
  { id: "profile", label: "Profile & location", icon: User },
  { id: "memory", label: "Memory", icon: Brain },
  { id: "data", label: "Your data", icon: Database },
] as const;

function SecretRow({ s, canEdit }: { s: SecretStatus; canEdit: boolean }) {
  const { setSecret, deleteSecret } = useSettings();
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      await setSecret(s.name, value.trim());
      setValue("");
      useToasts.getState().push({ kind: "success", title: `${s.label} saved`, body: "Stored encrypted on the server. It is never shown again." });
      void useSystem.getState().loadStatus();
    } catch (err) {
      useToasts.getState().error(err, "Couldn't save the key");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="py-3 border-b border-line last:border-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm text-ink flex items-center gap-2">
            <StatusDot ok={s.configured} /> {s.label}
          </p>
          <p className="text-[0.7rem] text-dim mt-0.5">
            {s.used_for} · <span className="font-mono">{s.name}</span>
            {s.configured && ` · ${s.source === "environment" ? "set in .env (read-only here)" : `saved ${s.hint}`}`}
          </p>
        </div>
        {s.configured && s.source === "stored" && canEdit && (
          <Button size="sm" variant="ghost" onClick={() => void deleteSecret(s.name).then(() => useSystem.getState().loadStatus())}>Remove</Button>
        )}
      </div>
      {canEdit && s.source !== "environment" && (
        <div className="flex gap-2 mt-2">
          <input type="password" autoComplete="off" spellCheck={false} className={inputClass} value={value}
            onChange={(e) => setValue(e.target.value)} placeholder={s.configured ? "Replace key…" : "Paste key…"} aria-label={s.label} />
          <Button onClick={() => void save()} loading={busy} disabled={value.trim().length < 8}>Save</Button>
        </div>
      )}
    </div>
  );
}

function Section({ id, title, icon, children }: { id: string; title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <Panel title={title} icon={icon} className="scroll-mt-4" bodyClassName="pb-5">
      <div id={id}>{children}</div>
    </Panel>
  );
}

export default function SettingsPage() {
  const { bundle, load, updateSection } = useSettings();
  const { serverStt, serverTts, wakeActive, setWake } = useVoice();
  const [error, setError] = useState<ApiError | null>(null);
  const [grants, setGrants] = useState<PermissionGrant[]>([]);
  const [apps, setApps] = useState<AppInfo[]>([]);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>(browserVoices());
  const [testing, setTesting] = useState(false);
  const [newRoot, setNewRoot] = useState("");
  const [newApp, setNewApp] = useState({ name: "", command: "", accepts_path: false });
  const [erase, setErase] = useState(false);
  const [eraseText, setEraseText] = useState("");

  const refresh = useCallback(async () => {
    try {
      await load();
      const [g, a] = await Promise.all([
        api.get<PermissionGrant[]>("/api/permissions/grants"), api.get<{ apps: AppInfo[] }>("/api/settings/apps"),
      ]);
      setGrants(g);
      setApps(a.apps);
      setError(null);
    } catch (err) {
      setError(ApiError.from(err));
    }
  }, [load]);

  useEffect(() => {
    void refresh();
    if (typeof speechSynthesis !== "undefined") speechSynthesis.onvoiceschanged = () => setVoices(browserVoices());
  }, [refresh]);

  const update = async <K extends keyof Preferences>(section: K, values: Partial<Preferences[K]>) => {
    try {
      await updateSection(section, values);
    } catch (err) {
      useToasts.getState().error(err, "Couldn't save the setting");
    }
  };

  if (error && !bundle) return <div className="p-6"><ErrorNotice title={error.message} reason={error.reason} nextStep={error.nextStep} onRetry={refresh} /></div>;
  if (!bundle) return <Spinner />;
  const p = bundle.preferences;
  const ai = bundle.ai;

  const testAi = async () => {
    setTesting(true);
    try {
      const res = await api.post<typeof ai>("/api/settings/test-ai");
      useToasts.getState().push(res.ready
        ? { kind: "success", title: "AI core online", body: `${res.provider} · ${res.model}` }
        : { kind: "error", title: res.error?.message ?? "AI core unreachable", detail: res.error?.next_step ?? undefined });
      await load();
      await useSystem.getState().loadStatus();
    } catch (err) {
      useToasts.getState().error(err);
    } finally {
      setTesting(false);
    }
  };

  const addRoot = async () => {
    if (!newRoot.trim()) return;
    await update("workspace", { roots: [...p.workspace.roots, newRoot.trim()] });
    setNewRoot("");
  };

  const addApp = async () => {
    const command = newApp.command.trim();
    if (!newApp.name.trim() || !command) return;
    await update("apps", { custom: [...p.apps.custom, { id: newApp.name, name: newApp.name.trim(), command: [command], accepts_path: newApp.accepts_path }] });
    setNewApp({ name: "", command: "", accepts_path: false });
    const a = await api.get<{ apps: AppInfo[] }>("/api/settings/apps");
    setApps(a.apps);
  };

  const exportData = async () => {
    try {
      const data = await api.get<unknown>("/api/settings/export");
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `nexus-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      useToasts.getState().error(err, "Export failed");
    }
  };

  const eraseAll = async () => {
    try {
      await api.post("/api/settings/erase", { confirm: eraseText });
      setErase(false);
      window.location.reload();
    } catch (err) {
      useToasts.getState().error(err);
    }
  };

  return (
    <div className="p-4 sm:p-6 max-w-6xl mx-auto">
      <PageHeader title="Settings" subtitle="Configure NEXUS. API keys stay on the server and are never shown again after saving." />
      <div className="grid gap-5 lg:grid-cols-[13rem_1fr]">
        <nav className="hidden lg:block sticky top-4 self-start space-y-0.5" aria-label="Settings sections">
          {SECTIONS.map(({ id, label, icon: Icon }) => (
            <a key={id} href={`#${id}`} className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-muted hover:text-ink hover:bg-white/[0.04]">
              <Icon className="size-4" /> {label}
            </a>
          ))}
        </nav>
        <div className="space-y-4 min-w-0">
          <Section id="ai" title="AI core" icon={<Cpu className="size-3.5" />}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm flex items-center gap-2">
                  <StatusDot ok={ai.ready} /> {ai.ready ? "Online" : ai.configured ? "Configured but unreachable" : "Not configured"}
                  {ai.mock && <Badge tone="warn">development mock</Badge>}
                </p>
                <p className="text-xs text-muted mt-1">
                  Provider <span className="font-mono">{ai.provider}</span>{ai.model && <> · model <span className="font-mono">{ai.model}</span></>}
                  {" "}· effort {ai.effort}{ai.refusal_fallback && " · refusal fallback on"}
                </p>
                {ai.error && <p className="text-xs text-amber mt-1">{ai.error.message} {ai.error.next_step}</p>}
              </div>
              <Button onClick={() => void testAi()} loading={testing}>Test connection</Button>
            </div>
            <p className="text-[0.7rem] text-dim mt-3">
              Change the provider or model with AI_PROVIDER / AI_MODEL in the backend .env. Without an AI key, NEXUS still handles
              reminders, tasks, memory, app launching, weather and file search.
            </p>
          </Section>

          <Section id="keys" title="API keys" icon={<KeyRound className="size-3.5" />}>
            {!bundle.can_edit_secrets && <p className="text-xs text-amber mb-2">Only an administrator can change API keys.</p>}
            {bundle.secrets.map((s) => <SecretRow key={s.name} s={s} canEdit={bundle.can_edit_secrets} />)}
          </Section>

          <Section id="voice" title="Voice" icon={<Mic className="size-3.5" />}>
            <div className="grid sm:grid-cols-2 gap-3 mb-2">
              <Field label="Speech-to-text" hint={serverStt ? `Server engine available: ${serverStt}` : "Server STT not configured — browser recognition is used."}>
                <select className={inputClass} value={p.voice.stt_provider} onChange={(e) => void update("voice", { stt_provider: e.target.value as Preferences["voice"]["stt_provider"] })}>
                  <option value="auto">Automatic</option>
                  <option value="server">Server (Whisper)</option>
                  <option value="browser">Browser</option>
                </select>
              </Field>
              <Field label="Text-to-speech" hint={serverTts ? `Server voice: ${serverTts}` : "Server voice not configured — browser voices are used."}>
                <select className={inputClass} value={p.voice.tts_provider} onChange={(e) => void update("voice", { tts_provider: e.target.value as Preferences["voice"]["tts_provider"] })}>
                  <option value="browser">Browser voice</option>
                  <option value="server" disabled={!serverTts}>Server voice</option>
                </select>
              </Field>
              <Field label="Browser voice">
                <select className={inputClass} value={p.voice.voice_name ?? ""} onChange={(e) => void update("voice", { voice_name: e.target.value || null })}>
                  <option value="">Automatic</option>
                  {voices.map((v) => <option key={v.name} value={v.name}>{v.name} ({v.lang})</option>)}
                </select>
              </Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label={`Rate ${p.voice.rate.toFixed(1)}×`}>
                  <input type="range" min={0.5} max={2} step={0.1} value={p.voice.rate} className="w-full accent-cyan"
                    onChange={(e) => void update("voice", { rate: Number(e.target.value) })} />
                </Field>
                <Field label={`Pitch ${p.voice.pitch.toFixed(1)}`}>
                  <input type="range" min={0.5} max={2} step={0.1} value={p.voice.pitch} className="w-full accent-cyan"
                    onChange={(e) => void update("voice", { pitch: Number(e.target.value) })} />
                </Field>
              </div>
            </div>
            <Button size="sm" onClick={() => void speak("Hello. NEXUS voice systems are working.", "browser", {
              voiceName: p.voice.voice_name, rate: p.voice.rate, pitch: p.voice.pitch })}>Preview voice</Button>
            <div className="mt-3 divide-y divide-line">
              <Toggle checked={p.voice.auto_speak} onChange={(v) => void update("voice", { auto_speak: v })} label="Speak every reply"
                description="Replies to voice requests are always spoken; turn this on to also speak typed conversations." />
              <Toggle
                checked={p.voice.wake_word_enabled}
                disabled={!WakeWordListener.supported()}
                onChange={(v) => {
                  void update("voice", { wake_word_enabled: v });
                  setWake(v);
                }}
                label="“Hey Nexus” wake phrase (experimental)"
                description={WakeWordListener.supported()
                  ? `Listens continuously while this tab is open, using your browser's speech service. ${wakeActive ? "Active now." : ""}`
                  : "Needs a browser with speech recognition (Chrome or Edge)."}
              />
            </div>
          </Section>

          <Section id="permissions" title="Permissions" icon={<ShieldCheck className="size-3.5" />}>
            <Toggle checked={p.permissions.confirm_medium_actions} onChange={(v) => void update("permissions", { confirm_medium_actions: v })}
              label="Ask before medium-risk actions"
              description="Editing files, running dev commands, creating AI automations. High-risk actions (deleting, installing, sending) always ask." />
            <p className="hud-label mt-4 mb-2">“Always allow” rules</p>
            {grants.length === 0 ? <p className="text-xs text-dim">None. When you choose “Always allow” on a request, the rule appears here.</p> : (
              <ul className="divide-y divide-line">
                {grants.map((g) => (
                  <li key={g.id} className="py-2 flex items-center gap-3 text-sm">
                    <div className="flex-1 min-w-0">
                      <p className="font-mono text-xs text-ink">{g.tool}</p>
                      <p className="text-[0.68rem] text-dim truncate">scope: {g.scope} · used {g.use_count}× · {timeAgo(g.created_at)}</p>
                    </div>
                    <Button size="sm" variant="ghost" onClick={async () => {
                      await api.del(`/api/permissions/grants/${g.id}`).catch((e) => useToasts.getState().error(e));
                      setGrants((x) => x.filter((y) => y.id !== g.id));
                    }}>Revoke</Button>
                  </li>
                ))}
              </ul>
            )}
            <p className="hud-label mt-4 mb-2">Approved commands</p>
            <ul className="grid sm:grid-cols-2 gap-1.5">
              {bundle.allowed_commands.map((c, i) => (
                <li key={`${c.program}-${i}`} className="text-xs flex items-center gap-2">
                  <span className="font-mono text-cyan/90">{c.program}</span>
                  <span className="text-dim truncate">{c.description}</span>
                  <Badge tone={c.risk === "high" ? "danger" : c.risk === "medium" ? "warn" : "ok"} className="ml-auto">{c.risk}</Badge>
                </li>
              ))}
            </ul>
          </Section>

          <Section id="workspace" title="Workspace folders & applications" icon={<FolderLock className="size-3.5" />}>
            {!bundle.computer_control && <p className="text-xs text-amber mb-3">Computer control is disabled on this server.</p>}
            <p className="text-xs text-muted mb-2">NEXUS can only read or change files inside these folders.</p>
            <ul className="space-y-1.5 mb-3">
              {bundle.env_workspace_roots.map((r) => (
                <li key={r} className="text-sm font-mono flex items-center gap-2"><Badge>.env</Badge>{r}</li>
              ))}
              {p.workspace.roots.map((r) => (
                <li key={r} className="text-sm font-mono flex items-center gap-2">
                  <span className="truncate">{r}</span>
                  {bundle.can_edit_host && (
                    <button className="ml-auto text-dim hover:text-rose" aria-label={`Remove ${r}`}
                      onClick={() => void update("workspace", { roots: p.workspace.roots.filter((x) => x !== r) })}>
                      <Trash2 className="size-3.5" />
                    </button>
                  )}
                </li>
              ))}
              {bundle.workspace_roots.length === 0 && <li className="text-xs text-dim">No folders authorised yet.</li>}
            </ul>
            {bundle.can_edit_host && (
              <div className="flex gap-2">
                <input className={inputClass} value={newRoot} onChange={(e) => setNewRoot(e.target.value)} placeholder="/home/you/projects"
                  onKeyDown={(e) => e.key === "Enter" && void addRoot()} aria-label="Folder to authorise" />
                <Button onClick={() => void addRoot()} icon={<Plus className="size-3.5" />}>Add</Button>
              </div>
            )}
            <p className="hud-label mt-5 mb-2 flex items-center gap-1.5"><AppWindow className="size-3" /> Applications NEXUS may open</p>
            <div className="flex flex-wrap gap-1.5">
              {apps.map((a) => (
                <span key={a.id} className={clsx("text-xs rounded-lg border px-2 py-1",
                  a.installed ? "border-ok/30 text-ink" : "border-line text-dim")} title={a.installed ? "Installed" : "Not found on this computer"}>
                  {a.name}{a.custom && " ·custom"}
                </span>
              ))}
            </div>
            {bundle.can_edit_host && (
              <div className="grid sm:grid-cols-[1fr_1.5fr_auto] gap-2 mt-3 items-end">
                <Field label="App name"><input className={inputClass} value={newApp.name} onChange={(e) => setNewApp({ ...newApp, name: e.target.value })} placeholder="Obsidian" /></Field>
                <Field label="Executable (full path)"><input className={inputClass} value={newApp.command} onChange={(e) => setNewApp({ ...newApp, command: e.target.value })} placeholder="/usr/bin/obsidian" /></Field>
                <Button onClick={() => void addApp()} icon={<Plus className="size-3.5" />}>Add app</Button>
              </div>
            )}
          </Section>

          <Section id="profile" title="Profile & location" icon={<MapPin className="size-3.5" />}>
            <div className="grid sm:grid-cols-2 gap-3">
              <Field label="Your name" hint="Used in greetings.">
                <input className={inputClass} defaultValue={p.profile.user_name ?? ""} maxLength={60}
                  onBlur={(e) => void update("profile", { user_name: e.target.value.trim() || null })} />
              </Field>
              <Field label="City" hint="Used for weather when you don't name a place.">
                <input className={inputClass} defaultValue={p.location.city ?? ""} maxLength={120}
                  onBlur={(e) => void update("location", { city: e.target.value.trim() || null, latitude: null, longitude: null })} />
              </Field>
              <Field label="Timezone" hint={`Blank = server timezone. Browser: ${Intl.DateTimeFormat().resolvedOptions().timeZone}`}>
                <input className={inputClass} defaultValue={p.regional.timezone ?? ""} placeholder={Intl.DateTimeFormat().resolvedOptions().timeZone}
                  onBlur={(e) => void update("regional", { timezone: e.target.value.trim() || null })} />
              </Field>
              <Field label="Units">
                <select className={inputClass} value={p.regional.units} onChange={(e) => void update("regional", { units: e.target.value as "metric" | "imperial" })}>
                  <option value="metric">Metric (°C, km/h)</option>
                  <option value="imperial">Imperial (°F, mph)</option>
                </select>
              </Field>
            </div>
          </Section>

          <Section id="memory" title="Memory" icon={<Brain className="size-3.5" />}>
            <Toggle checked={p.memory.auto_remember} onChange={(v) => void update("memory", { auto_remember: v })}
              label="Notice facts worth remembering"
              description="After each reply, NEXUS may suggest durable facts you mentioned (e.g. your college or project)." />
            <Toggle checked={p.memory.require_approval_for_inferred} onChange={(v) => void update("memory", { require_approval_for_inferred: v })}
              label="Ask before saving what NEXUS inferred"
              description="Recommended. Personal-sensitive facts always need approval; secrets are never stored." />
          </Section>

          <Section id="data" title="Your data" icon={<Database className="size-3.5" />}>
            <div className="flex flex-wrap gap-2">
              <Button icon={<Download className="size-3.5" />} onClick={() => void exportData()}>Export everything (JSON)</Button>
              <Button variant="danger" icon={<Trash2 className="size-3.5" />} onClick={() => setErase(true)}>Erase all my data</Button>
            </div>
            <p className="text-[0.7rem] text-dim mt-2">Data lives in your NEXUS database ({bundle.auth_mode === "local" ? "on this computer" : "your Supabase project"}).</p>
          </Section>
        </div>
      </div>

      <Modal open={erase} onClose={() => setErase(false)} title="Erase all data?" tone="danger"
        footer={<><Button variant="ghost" onClick={() => setErase(false)}>Cancel</Button>
          <Button variant="danger" disabled={eraseText !== "ERASE"} onClick={() => void eraseAll()}>Erase everything</Button></>}>
        <p className="text-sm text-muted mb-3">Deletes conversations, memories, tasks, automations, files, devices and settings. This cannot be undone.</p>
        <Field label="Type ERASE to confirm"><input className={inputClass} value={eraseText} onChange={(e) => setEraseText(e.target.value)} /></Field>
      </Modal>
    </div>
  );
}
