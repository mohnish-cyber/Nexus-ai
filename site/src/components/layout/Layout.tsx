import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Footer } from "./Footer";
import { Navbar } from "./Navbar";

/** Scrolls to "#section" after navigation (including cross-page "/#features" links), or to the top on page change. */
function ScrollManager() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) {
      const id = decodeURIComponent(hash.slice(1));
      // Wait a frame so the target page has rendered.
      const raf = requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }));
      return () => cancelAnimationFrame(raf);
    }
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [pathname, hash]);
  return null;
}

export function Layout() {
  return (
    <div className="relative flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only z-[100] rounded-full bg-accent px-4 py-2 text-sm font-medium text-white focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>
      <ScrollManager />
      <Navbar />
      <main id="main" className="flex-1">
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}
