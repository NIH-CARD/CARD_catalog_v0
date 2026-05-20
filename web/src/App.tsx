import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { CellularModelsPage } from "./pages/CellularModelsPage";
import { CodePage } from "./pages/CodePage";
import { DatasetsPage } from "./pages/DatasetsPage";
import { HomePage } from "./pages/HomePage";
import { PublicationsPage } from "./pages/PublicationsPage";
import { ResourcesPage } from "./pages/ResourcesPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/resources" element={<ResourcesPage />} />
        <Route path="/publications" element={<PublicationsPage />} />
        <Route path="/code" element={<CodePage />} />
        <Route path="/datasets/*" element={<DatasetsPage />} />
        <Route path="/cellular-models" element={<CellularModelsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
