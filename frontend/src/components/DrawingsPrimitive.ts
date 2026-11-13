import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesApi, ISeriesPrimitive, Logical, SeriesAttachedParameter, SeriesType, Time,
} from "lightweight-charts";
import { DEFAULT_COLOR, LABEL, distToSegment, formatPrice, timeToLogical, type Drawing, type DrawingPoint, type Px } from "../lib/drawings";

/**
 * Desenha as marcações DENTRO do gráfico. As coordenadas são recalculadas a cada
 * renderização com as escalas do próprio gráfico (tempo e preço), então os desenhos
 * acompanham zoom, pan e redimensionamento sem nenhuma sincronização manual.
 */
export class DrawingsPrimitive implements ISeriesPrimitive<Time> {
  private param?: SeriesAttachedParameter<Time, SeriesType>;
  private drawings: Drawing[] = [];
  private preview: Drawing | null = null;
  private selectedId: string | null = null;
  private times: number[] = [];

  private readonly renderer: IPrimitivePaneRenderer = { draw: (target) => this.draw(target) };
  private readonly view: IPrimitivePaneView = { zOrder: () => "top", renderer: () => this.renderer };

  attached(param: SeriesAttachedParameter<Time, SeriesType>) { this.param = param; }
  detached() { this.param = undefined; }
  paneViews() { return [this.view]; }

  set(state: { drawings: Drawing[]; preview: Drawing | null; selectedId: string | null; times: number[] }) {
    this.drawings = state.drawings; this.preview = state.preview; this.selectedId = state.selectedId; this.times = state.times;
    this.param?.requestUpdate();
  }

  private px(pt: DrawingPoint): Px | null {
    if (!this.param || this.times.length < 2) return null;
    const x = this.param.chart.timeScale().logicalToCoordinate(timeToLogical(this.times, pt.time) as Logical);
    const y = (this.param.series as ISeriesApi<SeriesType>).priceToCoordinate(Number(pt.price));
    return x == null || y == null ? null : { x, y };
  }

  /** Desenho sob o ponteiro (o mais recente tem prioridade), ou null. */
  findAt(p: Px, tolerance = 7): string | null {
    for (let i = this.drawings.length - 1; i >= 0; i--) {
      const d = this.drawings[i];
      const a = this.px(d.points[0]);
      if (!a) continue;
      let dist: number;
      if (d.type === "trend" || d.type === "ray") {
        const b = this.px(d.points[1]);
        if (!b) continue;
        dist = distToSegment(p, a, b, d.type === "ray");
      } else if (d.type === "marker") {
        dist = Math.hypot(p.x - a.x, p.y - a.y);
      } else {
        dist = Math.abs(p.y - a.y);
      }
      if (dist <= tolerance) return d.id;
    }
    return null;
  }

  private draw(target: CanvasRenderingTarget2D) {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const all = this.preview ? [...this.drawings, this.preview] : this.drawings;
      for (const d of all) this.drawOne(ctx, d, mediaSize.width, d === this.preview, d.id === this.selectedId);
    });
  }

  private drawOne(ctx: CanvasRenderingContext2D, d: Drawing, width: number, isPreview: boolean, selected: boolean) {
    const a = this.px(d.points[0]);
    if (!a) return;
    const color = d.color ?? DEFAULT_COLOR[d.type];
    ctx.save();
    ctx.strokeStyle = color; ctx.fillStyle = color;
    ctx.lineWidth = selected ? 3 : 2;
    ctx.globalAlpha = isPreview ? 0.6 : 1;
    ctx.font = "600 11px Inter, system-ui, sans-serif";

    if (d.type === "trend" || d.type === "ray") {
      const b = d.points[1] ? this.px(d.points[1]) : null;
      if (b) {
        let end = b;
        if (d.type === "ray" && b.x !== a.x) {   // prolonga até a borda direita mantendo a inclinação
          const k = (b.y - a.y) / (b.x - a.x);
          end = b.x > a.x ? { x: width, y: a.y + k * (width - a.x) } : b;
        }
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(end.x, end.y); ctx.stroke();
        if (selected) { this.dot(ctx, a); this.dot(ctx, b); }
      } else this.dot(ctx, a);
    } else if (d.type === "marker") {
      ctx.beginPath(); ctx.arc(a.x, a.y, selected ? 6 : 5, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = "#07131a"; ctx.lineWidth = 1.5; ctx.stroke();
      this.label(ctx, d.text || LABEL.marker, a.x + 10, a.y - 10, color, false);
    } else {
      ctx.setLineDash(d.type === "hline" ? [] : [7, 5]);
      ctx.beginPath(); ctx.moveTo(0, a.y); ctx.lineTo(width, a.y); ctx.stroke();
      ctx.setLineDash([]);
      this.label(ctx, `${d.text || LABEL[d.type]} ${formatPrice(d.points[0].price)}`, width - 8, a.y - 10, color, true);
      if (selected) this.dot(ctx, { x: 24, y: a.y });
    }
    ctx.restore();
  }

  private dot(ctx: CanvasRenderingContext2D, p: Px) {
    ctx.save(); ctx.fillStyle = "#07131a"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(p.x, p.y, 5, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); ctx.restore();
  }

  private label(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, color: string, alignRight: boolean) {
    const w = ctx.measureText(text).width + 12, h = 18;
    const left = alignRight ? x - w : x;
    ctx.save();
    ctx.fillStyle = "rgba(7,19,26,0.85)"; ctx.strokeStyle = color; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.roundRect(left, y - h / 2, w, h, 4); ctx.fill(); ctx.stroke();
    ctx.fillStyle = color; ctx.textBaseline = "middle"; ctx.fillText(text, left + 6, y);
    ctx.restore();
  }
}
