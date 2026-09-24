import { type FormEvent, useState } from "react";
import { Button, ErrorNotice, Field, inputClass } from "../components/common/ui";
import { NexusOrb } from "../components/orb/NexusOrb";
import { useAuth } from "../stores/authStore";

export default function LoginPage() {
  const { client, signIn, signUp, magicLink } = useAuth();
  const [mode, setMode] = useState<"signin" | "signup" | "magic">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      if (mode === "signin") await signIn(email, password);
      else if (mode === "signup") setMessage(await signUp(email, password));
      else {
        await magicLink(email);
        setMessage("Check your email for a sign-in link.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="h-full nexus-backdrop flex items-center justify-center p-6 overflow-y-auto">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-6">
          <NexusOrb state="idle" size={140} />
          <h1 className="text-2xl font-semibold tracking-[0.45em] pl-[0.45em] mt-2">NEXUS</h1>
          <p className="text-xs text-muted mt-1">Sign in to your personal AI operating system</p>
        </div>
        {!client ? (
          <ErrorNotice title="Sign-in is not configured on this server."
            nextStep="Set SUPABASE_URL and SUPABASE_ANON_KEY in the backend .env, or use AUTH_MODE=local." />
        ) : (
          <form onSubmit={submit} className="glass rounded-2xl p-5 space-y-3">
            <Field label="Email">
              <input className={inputClass} type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            {mode !== "magic" && (
              <Field label="Password">
                <input className={inputClass} type="password" required minLength={8} autoComplete={mode === "signup" ? "new-password" : "current-password"}
                  value={password} onChange={(e) => setPassword(e.target.value)} />
              </Field>
            )}
            {error && <p className="text-xs text-rose">{error}</p>}
            {message && <p className="text-xs text-ok">{message}</p>}
            <Button variant="primary" type="submit" loading={busy} className="w-full">
              {mode === "signin" ? "Sign in" : mode === "signup" ? "Create account" : "Email me a link"}
            </Button>
            <div className="flex justify-between text-xs text-muted pt-1">
              <button type="button" onClick={() => setMode(mode === "signup" ? "signin" : "signup")} className="hover:text-ink">
                {mode === "signup" ? "Have an account? Sign in" : "Create an account"}
              </button>
              <button type="button" onClick={() => setMode(mode === "magic" ? "signin" : "magic")} className="hover:text-ink">
                {mode === "magic" ? "Use password" : "Magic link"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
