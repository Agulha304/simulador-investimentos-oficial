import { useNavigate } from "react-router-dom";
import { gameStore } from "../services/gameStore";

/** Fim de jogo: morte do personagem ou falência. A partida fica guardada, mas não avança mais. */
export function EndScreen({ reason, name, age }: { reason: string; name: string; age?: number | null }) {
  const nav = useNavigate();
  const dead = reason === "DEAD";
  return (
    <div className="modal-back" role="dialog" aria-modal="true" aria-label="Fim de jogo">
      <div className="card modal center">
        <div style={{ fontSize: "4rem" }}>{dead ? "🕊️" : "📉"}</div>
        <h2>{dead ? "Fim de jogo: o seu personagem faleceu" : "Fim de jogo: falência"}</h2>
        <p>{dead ? `${name} viveu ${age ?? ""} anos. Cuidar da saúde, do descanso e da família aumenta a chance de uma vida longa.` : "O saldo negativo passou de R$ 100 mil e você não conseguiu mais pagar as contas. Planejar gastos, reserva de emergência e evitar o cheque especial teriam ajudado."}</p>
        <p className="muted small">A partida continua guardada para você consultar relatórios e desempenho, mas não avança mais.</p>
        <div className="row" style={{ justifyContent: "center" }}>
          <button className="btn primary" onClick={() => { gameStore.set(null); nav("/partida/nova"); }}>🎮 Começar uma nova partida</button>
          <button className="btn ghost" onClick={() => { gameStore.set(null); nav("/"); }}>Voltar ao menu</button>
        </div>
      </div>
    </div>
  );
}
