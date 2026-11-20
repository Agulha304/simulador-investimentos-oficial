import { useEffect } from "react";

/** Aviso temporário (some sozinho). Usado para contar o que aconteceu na convivência com as pessoas. */
export function Toast({ text, onClose, seconds = 7 }: { text: string; onClose: () => void; seconds?: number }) {
  useEffect(() => { const t = window.setTimeout(onClose, seconds * 1000); return () => window.clearTimeout(t); }, [text, onClose, seconds]);
  return (
    <div className="toast" role="status" aria-live="polite" onClick={onClose}>
      <span className="toast-emoji" aria-hidden>✨</span><span>{text}</span>
    </div>
  );
}
