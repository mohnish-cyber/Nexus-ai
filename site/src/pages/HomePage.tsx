import { Commands } from "../components/home/Commands";
import { Features } from "../components/home/Features";
import { FinalCta } from "../components/home/FinalCta";
import { Hero } from "../components/home/Hero";
import { HowItWorks } from "../components/home/HowItWorks";
import { Integrations } from "../components/home/Integrations";
import { Privacy } from "../components/home/Privacy";
import { Faq } from "../components/faq/Faq";
import { PricingSection } from "../components/pricing/PricingSection";
import { useDocumentTitle } from "../lib/useDocumentTitle";
import { useReveal } from "../lib/useReveal";

export function HomePage() {
  useDocumentTitle();
  useReveal();
  return (
    <>
      <Hero />
      <Integrations />
      <Features />
      <Privacy />
      <HowItWorks />
      <Commands />
      <PricingSection />
      <Faq />
      <FinalCta />
    </>
  );
}
