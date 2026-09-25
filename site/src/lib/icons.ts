import {
  Activity,
  AlarmClock,
  Brain,
  Code2,
  FileText,
  FolderLock,
  Globe,
  HardDrive,
  KeyRound,
  Mic,
  MonitorSmartphone,
  Network,
  ScanEye,
  ScrollText,
  ShieldCheck,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

/** Maps the icon names used in content.ts to lucide components. */
const registry: Record<string, LucideIcon> = {
  Activity,
  AlarmClock,
  Brain,
  Code2,
  FileText,
  FolderLock,
  Globe,
  HardDrive,
  KeyRound,
  Mic,
  MonitorSmartphone,
  Network,
  ScanEye,
  ScrollText,
  ShieldCheck,
};

export function iconFor(name: string): LucideIcon {
  return registry[name] ?? Sparkles;
}
