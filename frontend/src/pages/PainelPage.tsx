import { useActiveGame } from "../services/gameStore";
import { OverviewPage } from "./OverviewPage";
import { TrainingHome } from "./TrainingHome";

export function PainelPage() {
  const g = useActiveGame();
  return g?.kind === "TRAINING" ? <TrainingHome /> : <OverviewPage />;
}
