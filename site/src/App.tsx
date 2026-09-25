import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { DocsPage } from "./pages/DocsPage";
import { HomePage } from "./pages/HomePage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { PricingPage } from "./pages/PricingPage";
import { StatusPage } from "./pages/StatusPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="pricing" element={<PricingPage />} />
        <Route path="docs" element={<DocsPage />} />
        <Route path="status" element={<StatusPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
