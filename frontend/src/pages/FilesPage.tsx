import clsx from "clsx";
import { AlertTriangle, FileCode2, FileText, Image as ImageIcon, Loader2, MessageSquare, Trash2, UploadCloud } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Badge, Button, EmptyState, ErrorNotice, PageHeader, Panel, Spinner } from "../components/common/ui";
import { bytes, timeAgo } from "../lib/format";
import { ApiError, api } from "../services/api";
import { useSystem } from "../stores/systemStore";
import { useToasts } from "../stores/toastStore";
import type { FileInfo } from "../types/api";

function KindIcon({ kind }: { kind: FileInfo["kind"] }) {
  if (kind === "image") return <ImageIcon className="size-5 text-violet" />;
  if (kind === "code") return <FileCode2 className="size-5 text-mint" />;
  return <FileText className="size-5 text-cyan" />;
}

export default function FilesPage() {
  const [files, setFiles] = useState<FileInfo[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [uploading, setUploading] = useState<string[]>([]);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const maxMb = useSystem((s) => s.config?.max_upload_mb ?? 25);

  const load = useCallback(async () => {
    try {
      setFiles(await api.get<FileInfo[]>("/api/files"));
      setError(null);
    } catch (err) {
      setError(ApiError.from(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const upload = async (list: File[]) => {
    for (const file of list) {
      setUploading((u) => [...u, file.name]);
      const form = new FormData();
      form.append("file", file);
      try {
        const info = await api.upload<FileInfo>("/api/files", form);
        setFiles((f) => [info, ...(f ?? [])]);
        if (info.status === "failed") useToasts.getState().push({ kind: "error", title: `${file.name} couldn't be read`, detail: info.error ?? undefined });
      } catch (err) {
        useToasts.getState().error(err, `Upload failed: ${file.name}`);
      } finally {
        setUploading((u) => u.filter((n) => n !== file.name));
      }
    }
  };

  const del = async (f: FileInfo) => {
    if (!window.confirm(`Delete ${f.filename}?`)) return;
    try {
      await api.del(`/api/files/${f.id}`);
      setFiles((x) => x?.filter((y) => y.id !== f.id) ?? null);
    } catch (err) {
      useToasts.getState().error(err, "Couldn't delete the file");
    }
  };

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto">
      <PageHeader title="Files" subtitle="Upload PDFs, Word documents, notes, code or images. NEXUS reads them and answers questions with page references." />
      <button
        onClick={() => input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); void upload(Array.from(e.dataTransfer.files)); }}
        className={clsx("w-full glass rounded-2xl border-dashed border-2 py-10 flex flex-col items-center gap-2 transition mb-4",
          drag ? "border-cyan/70 bg-cyan/5" : "border-line-strong hover:border-cyan/40")}
      >
        <UploadCloud className="size-8 text-cyan" />
        <p className="text-sm text-ink">Drop files here or click to upload</p>
        <p className="text-xs text-dim">PDF · DOCX · TXT/MD · code · PNG/JPG/WebP — up to {maxMb} MB. Files are checked by content and stored privately.</p>
      </button>
      <input ref={input} type="file" multiple hidden onChange={(e) => { void upload(Array.from(e.target.files ?? [])); e.target.value = ""; }} />

      {uploading.length > 0 && (
        <div className="mb-4 space-y-1">
          {uploading.map((n) => (
            <p key={n} className="text-xs text-muted flex items-center gap-2"><Loader2 className="size-3.5 animate-spin text-cyan" /> Processing {n}…</p>
          ))}
        </div>
      )}

      <Panel title="Your files">
        {error ? <ErrorNotice title={error.message} reason={error.reason} nextStep={error.nextStep} onRetry={load} /> :
          files === null ? <Spinner /> : files.length === 0 ? (
            <EmptyState icon={<FileText className="size-6" />} title="No files yet">
              Upload a syllabus and ask “Explain Unit 3 simply”, or a screenshot and ask “What's wrong here?”.
            </EmptyState>
          ) : (
            <ul className="divide-y divide-line">
              {files.map((f) => (
                <li key={f.id} className="py-3 flex items-start gap-3">
                  <KindIcon kind={f.kind} />
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm text-ink truncate">{f.filename}</p>
                      <Badge tone={f.status === "ready" ? "ok" : f.status === "failed" ? "danger" : "cyan"}>{f.status}</Badge>
                    </div>
                    <p className="text-[0.7rem] text-dim mt-0.5">
                      {f.kind.toUpperCase()} · {bytes(f.size_bytes)}{f.page_count ? ` · ${f.page_count} pages` : ""}
                      {f.chunks ? ` · ${f.chunks} passages indexed` : ""} · {timeAgo(f.created_at)}
                    </p>
                    {f.error && <p className="text-xs text-rose/90 mt-1 flex gap-1.5"><AlertTriangle className="size-3.5 shrink-0 mt-0.5" />{f.error}</p>}
                    {f.sections.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {f.sections.slice(0, 8).map((s, i) => <Badge key={`${s}-${i}`}>{s.length > 40 ? `${s.slice(0, 40)}…` : s}</Badge>)}
                        {f.sections.length > 8 && <Badge>+{f.sections.length - 8}</Badge>}
                      </div>
                    )}
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <Button size="sm" disabled={f.status !== "ready"} icon={<MessageSquare className="size-3.5" />}
                      onClick={() => navigate("/assistant", { state: { attach: [f] } })}>Ask</Button>
                    <button onClick={() => void del(f)} className="p-1.5 text-dim hover:text-rose" aria-label={`Delete ${f.filename}`}>
                      <Trash2 className="size-4" />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
      </Panel>
    </div>
  );
}
