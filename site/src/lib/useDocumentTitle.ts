import { useEffect } from "react";
import { site } from "../content";

/** Sets the tab title to "<title> · NEXUS", or the default title when omitted. */
export function useDocumentTitle(title?: string): void {
  useEffect(() => {
    document.title = title ? `${title} · ${site.name}` : `${site.name} — ${site.tagline}`;
  }, [title]);
}
