import { Bot, Brain, FolderOpen, Home, ListChecks, MessageSquare, MonitorSmartphone, Settings, Workflow } from "lucide-react";

export const NAV = [
  { to: "/", label: "Home", icon: Home },
  { to: "/assistant", label: "Assistant", icon: MessageSquare },
  { to: "/tasks", label: "Tasks", icon: ListChecks },
  { to: "/memory", label: "Memory", icon: Brain },
  { to: "/files", label: "Files", icon: FolderOpen },
  { to: "/automations", label: "Automations", icon: Workflow },
  { to: "/agents", label: "Agents", icon: Bot },
  { to: "/devices", label: "Devices", icon: MonitorSmartphone },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

export const MOBILE_NAV = ["/", "/assistant", "/tasks", "/memory", "/settings"];
