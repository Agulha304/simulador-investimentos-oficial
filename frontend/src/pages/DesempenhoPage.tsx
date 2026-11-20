import { useActiveGame } from "../services/gameStore";
import { CareerPerformancePage } from "./CareerPerformancePage";
import { PerformancePage } from "./PerformancePage";

/** Treino mostra o desempenho dos INVESTIMENTOS; a partida de vida completa mostra o desempenho da CARREIRA. */
export function DesempenhoPage() {
  const g = useActiveGame();
  return g?.kind === "LIFE" ? <CareerPerformancePage /> : <PerformancePage />;
}
