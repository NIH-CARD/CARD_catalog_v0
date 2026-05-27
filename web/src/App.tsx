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

const STREAMLIT_URL = "https://card-catalog-v0.streamlit.app";

function UpdateBanner() {
  return (
    <div className="bg-amber-50 border-b border-amber-300 px-4 py-2 flex items-center justify-center gap-2 text-sm text-amber-900">
      <span className="text-amber-500 text-base">⚠</span>
      <span>
        This app is currently being updated and may be missing features.
        Visit the full version at the{" "}
        <a
          href={STREAMLIT_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="font-semibold underline hover:text-amber-700"
        >
          Streamlit app
        </a>
        .
      </span>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter basename={BASENAME}>
      <UpdateBanner />
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
