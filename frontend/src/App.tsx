import { Suspense, lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { GameLayout } from "./components/GameLayout";
import { HubLayout } from "./components/HubLayout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { BudgetPage } from "./pages/BudgetPage";
import { CompaniesPage } from "./pages/CompaniesPage";
import { CompanyPage } from "./pages/CompanyPage";
import { GoodPage } from "./pages/GoodPage";
import { WealthPage } from "./pages/WealthPage";
import { AuthPage } from "./pages/AuthPage";
import { LearnPage } from "./pages/LearnPage";
import { LessonPage } from "./pages/LessonPage";
import { MarketPage } from "./pages/MarketPage";
import { FixedIncomePage } from "./pages/FixedIncomePage";
import { HistoryPage } from "./pages/HistoryPage";
import { PortfolioPage } from "./pages/PortfolioPage";
import { RankingPage } from "./pages/RankingPage";
import { EconomyPage } from "./pages/EconomyPage";
import { LifePage } from "./pages/LifePage";
import { DesempenhoPage } from "./pages/DesempenhoPage";
import { AchievementsPage } from "./pages/AchievementsPage";
import { HubPage } from "./pages/HubPage";
import { NewGamePage } from "./pages/NewGamePage";
import { NewTrainingPage } from "./pages/NewTrainingPage";
import { SettingsPage } from "./pages/SettingsPage";
import { PainelPage } from "./pages/PainelPage";
import { ReportsPage } from "./pages/ReportsPage";
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
            {/* fora da partida: menu inicial, aulas, ranking e conquistas */}
            <Route element={<HubLayout />}>
              <Route index element={<HubPage />} />
              <Route path="partida/nova" element={<NewGamePage />} />
              <Route path="treino/novo" element={<NewTrainingPage />} />
              <Route path="aulas" element={<LearnPage />} />
              <Route path="aulas/:id" element={<LessonPage />} />
              <Route path="ranking" element={<RankingPage />} />
              <Route path="conquistas" element={<AchievementsPage />} />
              <Route path="configuracoes" element={<SettingsPage />} />
            </Route>
            {/* dentro da partida */}
            <Route element={<GameLayout />}>
              <Route path="painel" element={<PainelPage />} />
              <Route path="orcamento" element={<BudgetPage />} />
              <Route path="mercado" element={<MarketPage />} />
              <Route path="renda-fixa" element={<FixedIncomePage />} />
              <Route path="carteira" element={<PortfolioPage />} />
              <Route path="historico" element={<HistoryPage />} />
              <Route path="ativo/:id" element={<AssetPage />} />
              <Route path="empresas" element={<CompaniesPage />} />
              <Route path="empresas/:id" element={<CompanyPage />} />
              <Route path="patrimonio" element={<WealthPage group="goods" />} />
              <Route path="imoveis" element={<WealthPage group="realty" />} />
              <Route path="automoveis" element={<WealthPage group="vehicles" />} />
              <Route path="patrimonio/:id" element={<GoodPage />} />
              <Route path="vida" element={<LifePage />} />
              <Route path="economia" element={<EconomyPage />} />
              <Route path="resumos" element={<ReportsPage />} />
              <Route path="desempenho" element={<DesempenhoPage />} />
              <Route path="desempenho/investimentos" element={<PerformancePage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
      </BrowserRouter>
    </AuthProvider>
  );
}
