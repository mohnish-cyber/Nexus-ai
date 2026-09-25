import { ArrowLeft } from "lucide-react";
import { ButtonLink } from "../components/ui/Button";
import { Container } from "../components/ui/Container";
import { useDocumentTitle } from "../lib/useDocumentTitle";

export function NotFoundPage() {
  useDocumentTitle("Page not found");
  return (
    <section className="relative overflow-hidden pt-40 pb-32">
      <div className="bg-grid pointer-events-none absolute inset-0" aria-hidden />
      <Container className="relative flex flex-col items-center text-center">
        <span className="font-mono text-sm text-accent-soft">404</span>
        <h1 className="text-gradient mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">This page wandered off.</h1>
        <p className="mt-4 max-w-md text-fg-muted">
          Even NEXUS couldn't find it. Check the address, or head back to the start.
        </p>
        <ButtonLink href="/" variant="secondary" className="mt-8">
          <ArrowLeft className="size-4" /> Back home
        </ButtonLink>
      </Container>
    </section>
  );
}
