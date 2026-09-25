// STUB: replaced by the section builder. Keep this prop signature.
import { faqs } from "../../content";

export type FaqItem = { q: string; a: string };

export function Faq({
  id = "faq",
  eyebrow = "FAQ",
  title = "Questions, answered",
  items = faqs,
}: {
  id?: string;
  eyebrow?: string;
  title?: string;
  items?: FaqItem[];
}) {
  return (
    <section id={id} className="py-24 text-center text-fg-dim">
      {eyebrow} {title} ({items.length})
    </section>
  );
}
