import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AboutPage } from "./pages/AboutPage";
import { CellularModelsPage } from "./pages/CellularModelsPage";
import { CodePage } from "./pages/CodePage";
import { DatasetsPage } from "./pages/DatasetsPage";
import { HomePage } from "./pages/HomePage";
import { PublicationsPage } from "./pages/PublicationsPage";
import { ResourcesPage } from "./pages/ResourcesPage";

// import.meta.env.BASE_URL is "/" in dev and "/CARD_catalog_v0/" in build.
// React Router wants the basename without the trailing slash.
const BASENAME = import.meta.env.BASE_URL.replace(/\/$/, "");

export default function App() {
  return (
    <BrowserRouter basename={BASENAME}>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/resources" element={<ResourcesPage />} />
        <Route path="/publications" element={<PublicationsPage />} />
        <Route path="/code" element={<CodePage />} />
        <Route path="/datasets/*" element={<DatasetsPage />} />
        <Route path="/cellular-models" element={<CellularModelsPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
