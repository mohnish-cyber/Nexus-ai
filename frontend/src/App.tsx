import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { BootSequence } from "./components/boot/BootSequence";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { Toaster } from "./components/common/Toaster";
import { Button, ErrorNotice, Spinner } from "./components/common/ui";
import { MobileNav } from "./components/layout/MobileNav";
import { Sidebar } from "./components/layout/Sidebar";
import { TopBar } from "./components/layout/TopBar";
import { PermissionDialog } from "./components/permissions/PermissionDialog";
import { useBackgroundSync } from "./hooks/useBackgroundSync";
import { useSpeechOutput } from "./hooks/useSpeechOutput";
import LoginPage from "./pages/LoginPage";
import { ApiError } from "./services/api";
import { useAuth } from "./stores/authStore";
import { useSystem } from "./stores/systemStore";

const HomePage = lazy(() => import("./pages/HomePage"));
const AssistantPage = lazy(() => import("./pages/AssistantPage"));
const TasksPage = lazy(() => import("./pages/TasksPage"));
const MemoryPage = lazy(() => import("./pages/MemoryPage"));
const FilesPage = lazy(() => import("./pages/FilesPage"));
const AutomationsPage = lazy(() => import("./pages/AutomationsPage"));
const AgentsPage = lazy(() => import("./pages/AgentsPage"));
const DevicesPage = lazy(() => import("./pages/DevicesPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

function page(name: string, el: React.ReactNode) {
  return (
    <ErrorBoundary scope={name}>
      <Suspense fallback={<Spinner />}>{el}</Suspense>
    </ErrorBoundary>
  );
}

function Shell() {
  useBackgroundSync();
  useSpeechOutput();
  return (
    <div className="h-full flex nexus-backdrop">
      <Sidebar />
      <div className="flex-1 min-w-0 flex flex-col">
        <TopBar />
        <main className="flex-1 min-h-0 overflow-y-auto scrollbar-thin pb-20 lg:pb-0">
          <Routes>
            <Route path="/" element={page("Home", <HomePage />)} />
            <Route path="/assistant" element={page("Assistant", <AssistantPage />)} />
            <Route path="/assistant/:conversationId" element={page("Assistant", <AssistantPage />)} />
            <Route path="/tasks" element={page("Tasks", <TasksPage />)} />
            <Route path="/memory" element={page("Memory", <MemoryPage />)} />
            <Route path="/files" element={page("Files", <FilesPage />)} />
            <Route path="/automations" element={page("Automations", <AutomationsPage />)} />
            <Route path="/agents" element={page("Agents", <AgentsPage />)} />
            <Route path="/devices" element={page("Devices", <DevicesPage />)} />
            <Route path="/settings" element={page("Settings", <SettingsPage />)} />
            <Route path="*" element={page("Home", <HomePage />)} />
          </Routes>
        </main>
      </div>
      <MobileNav />
      <PermissionDialog />
    </div>
  );
}

export default function App() {
  const [bootError, setBootError] = useState<ApiError | null>(null);
  const [booted, setBooted] = useState(() => sessionStorage.getItem("nexus.booted") === "1");
  const { ready, mode, session } = useAuth();

  const start = useCallback(async () => {
    setBootError(null);
    try {
      const config = await useSystem.getState().loadConfig();
      await useAuth.getState().init(config);
    } catch (err) {
      setBootError(ApiError.from(err));
    }
  }, []);

  useEffect(() => {
    void start();
  }, [start]);

  const finishBoot = useCallback(() => {
    sessionStorage.setItem("nexus.booted", "1");
    setBooted(true);
  }, []);

  if (bootError) {
    return (
      <div className="h-full nexus-backdrop flex items-center justify-center p-6">
        <div className="max-w-md w-full space-y-4 text-center">
          <h1 className="text-2xl font-semibold tracking-[0.4em]">NEXUS</h1>
          <ErrorNotice title={bootError.message} reason={bootError.reason} nextStep={bootError.nextStep} />
          <Button variant="primary" onClick={() => void start()}>Retry</Button>
        </div>
      </div>
    );
  }
  if (!ready) return <div className="h-full nexus-backdrop"><Spinner label="Connecting to NEXUS…" /></div>;
  if (mode === "supabase" && !session) return <><LoginPage /><Toaster /></>;

  return (
    <>
      <Shell />
      {!booted && <BootSequence onDone={finishBoot} />}
      <Toaster />
    </>
  );
}
