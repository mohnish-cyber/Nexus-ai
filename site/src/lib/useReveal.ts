import { useEffect } from "react";

/**
 * Fades in every element marked with the `data-reveal` attribute as it scrolls into view.
 * Call once per page. Add `style={{ "--reveal-delay": "120ms" }}` to stagger siblings.
 */
export function useReveal(deps: unknown[] = []): void {
  useEffect(() => {
    const els = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal]:not([data-reveal='visible'])"));
    if (!("IntersectionObserver" in window)) {
      els.forEach((el) => (el.dataset.reveal = "visible"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            (entry.target as HTMLElement).dataset.reveal = "visible";
            io.unobserve(entry.target);
          }
        }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
