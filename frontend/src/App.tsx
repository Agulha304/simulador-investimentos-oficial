import { Suspense, lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { BudgetPage } from "./pages/BudgetPage";
import { CompaniesPage } from "./pages/CompaniesPage";
import { CompanyPage } from "./pages/CompanyPage";
import { GoodPage } from "./pages/GoodPage";
import { WealthPage } from "./pages/WealthPage";
import { AuthPage } from "./pages/AuthPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LearnPage } from "./pages/LearnPage";
import { LessonPage } from "./pages/LessonPage";
import { MarketPage } from "./pages/MarketPage";
import { FixedIncomePage } from "./pages/FixedIncomePage";
import { HistoryPage } from "./pages/HistoryPage";
import { PortfolioPage } from "./pages/PortfolioPage";
import { RankingPage } from "./pages/RankingPage";
import { AuthProvider } from "./services/auth";

// páginas com bibliotecas de gráficos pesadas são carregadas só quando visitadas
const AssetPage = lazy(() => import("./pages/AssetPage").then((m) => ({ default: m.AssetPage })));
const PerformancePage = lazy(() => import("./pages/PerformancePage").then((m) => ({ default: m.PerformancePage })));

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Suspense fallback={<div className="center-screen muted">Carregando…</div>}>
        <Routes>
          <Route path="/login" element={<AuthPage mode="login" />} />
          <Route path="/cadastro" element={<AuthPage mode="register" />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<Layout />}>
              <Route index element={<DashboardPage />} />
              <Route path="mercado" element={<MarketPage />} />
              <Route path="carteira" element={<PortfolioPage />} />
              <Route path="orcamento" element={<BudgetPage />} />
              <Route path="patrimonio" element={<WealthPage />} />
              <Route path="empresas" element={<CompaniesPage />} />
              <Route path="empresas/:id" element={<CompanyPage />} />
              <Route path="patrimonio/:id" element={<GoodPage />} />
              <Route path="renda-fixa" element={<FixedIncomePage />} />
              <Route path="desempenho" element={<PerformancePage />} />
              <Route path="ranking" element={<RankingPage />} />
              <Route path="aulas" element={<LearnPage />} />
              <Route path="aulas/:id" element={<LessonPage />} />
              <Route path="historico" element={<HistoryPage />} />
              <Route path="ativo/:id" element={<AssetPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
      </BrowserRouter>
    </AuthProvider>
  );
}
