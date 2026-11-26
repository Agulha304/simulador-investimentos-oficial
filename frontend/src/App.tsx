import { Suspense, lazy, useEffect, type ComponentType } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { GameLayout } from "./components/GameLayout";
import { HubLayout } from "./components/HubLayout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AuthPage } from "./pages/AuthPage";
import { HubPage } from "./pages/HubPage";
import { AuthProvider } from "./services/auth";

// todas as páginas (exceto layouts, login e hub) são carregadas sob demanda; recharts/lightweight-charts só vêm com as que os usam
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const page = <K extends string>(load: () => Promise<Record<K, ComponentType<any>>>, name: K) => lazy(() => load().then((m) => ({ default: m[name] })));
const imports = {
  PainelPage: () => import("./pages/PainelPage"), MarketPage: () => import("./pages/MarketPage"),
  FixedIncomePage: () => import("./pages/FixedIncomePage"), PortfolioPage: () => import("./pages/PortfolioPage"), HistoryPage: () => import("./pages/HistoryPage"),
  AssetPage: () => import("./pages/AssetPage"),
};
const ForgotPasswordPage = page(() => import("./pages/ForgotPasswordPage"), "ForgotPasswordPage");
const ResetPasswordPage = page(() => import("./pages/ResetPasswordPage"), "ResetPasswordPage");
const AssetPage = page(imports.AssetPage, "AssetPage");
const PerformancePage = page(() => import("./pages/PerformancePage"), "PerformancePage");
const PainelPage = page(imports.PainelPage, "PainelPage");
const BudgetPage = page(() => import("./pages/BudgetPage"), "BudgetPage");
const MarketPage = page(imports.MarketPage, "MarketPage");
const FixedIncomePage = page(imports.FixedIncomePage, "FixedIncomePage");
const PortfolioPage = page(imports.PortfolioPage, "PortfolioPage");
const HistoryPage = page(imports.HistoryPage, "HistoryPage");
const CareerPage = page(() => import("./pages/CareerPage"), "CareerPage");
const EducationPage = page(() => import("./pages/EducationPage"), "EducationPage");
const WorldPage = page(() => import("./pages/WorldPage"), "WorldPage");
const CompaniesPage = page(() => import("./pages/CompaniesPage"), "CompaniesPage");
const CompanyPage = page(() => import("./pages/CompanyPage"), "CompanyPage");
const GoodPage = page(() => import("./pages/GoodPage"), "GoodPage");
const WealthPage = page(() => import("./pages/WealthPage"), "WealthPage");
const LearnPage = page(() => import("./pages/LearnPage"), "LearnPage");
const LessonPage = page(() => import("./pages/LessonPage"), "LessonPage");
const RankingPage = page(() => import("./pages/RankingPage"), "RankingPage");
const EconomyPage = page(() => import("./pages/EconomyPage"), "EconomyPage");
const LifePage = page(() => import("./pages/LifePage"), "LifePage");
const DesempenhoPage = page(() => import("./pages/DesempenhoPage"), "DesempenhoPage");
const AchievementsPage = page(() => import("./pages/AchievementsPage"), "AchievementsPage");
const NewGamePage = page(() => import("./pages/NewGamePage"), "NewGamePage");
const NewTrainingPage = page(() => import("./pages/NewTrainingPage"), "NewTrainingPage");
const SettingsPage = page(() => import("./pages/SettingsPage"), "SettingsPage");
const ReportsPage = page(() => import("./pages/ReportsPage"), "ReportsPage");

/** Com o navegador ocioso, baixa os chunks das telas mais usadas (sem recharts) para a primeira navegação ser instantânea. */
function usePrefetch() {
  useEffect(() => {
    const run = () => Object.values(imports).forEach((f) => { void f().catch(() => undefined); });
    const w = window as Window & { requestIdleCallback?: (cb: () => void) => number };
    if (w.requestIdleCallback) w.requestIdleCallback(run); else setTimeout(run, 2000);
  }, []);
}

export default function App() {
  usePrefetch();
  return (
    <AuthProvider>
      <BrowserRouter>
        <Suspense fallback={<div className="center-screen muted">Carregando…</div>}>
        <Routes>
          <Route path="/login" element={<AuthPage mode="login" />} />
          <Route path="/cadastro" element={<AuthPage mode="register" />} />
          <Route path="/esqueci-senha" element={<ForgotPasswordPage />} />
          <Route path="/redefinir-senha" element={<ResetPasswordPage />} />
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
              <Route path="carreira" element={<CareerPage />} />
              <Route path="educacao" element={<EducationPage />} />
              <Route path="mundo" element={<WorldPage />} />
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
