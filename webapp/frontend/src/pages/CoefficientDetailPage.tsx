import { useState } from "react";
import {
  ArrowLeft,
  Database,
  Info,
  RefreshCw,
  Sigma,
  Table2,
  Wrench,
} from "lucide-react";
import { PageHeader } from "../components/layout/PageHeader";
import { SectionCard, ResultTile } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { InlineNotice } from "../components/ui/State";
import {
  useBackendComparison,
  useCoefficientCompare,
  useReferenceTables,
  useTablePoint,
} from "../hooks/queries";
import { useAppStore } from "../store/useAppStore";
import { fmt, num } from "../lib/format";
import { cn } from "../lib/utils";

export function CoefficientDetailPage() {
  const inputs = useAppStore((state) => state.inputs);
  const results = useAppStore((state) => state.results);
  const setTab = useAppStore((state) => state.setTab);
  const pushToast = useAppStore((state) => state.pushToast);

  const { data: referenceTables } = useReferenceTables();
  const compare = useCoefficientCompare();
  const backendCompare = useBackendComparison();
  const tablePoint = useTablePoint();

  const [compareError, setCompareError] = useState<string | null>(null);

  const institutional = referenceTables?.items.find((table) => table.key === "institutional");
  const gail = referenceTables?.items.find((table) => table.key === "gail");
  const bCompare = results.bCompare;

  function runCompare() {
    if (inputs.pressure.temperature_c === null || inputs.pressure.pressure_bar === null) {
      pushToast("error", "Karşılaştırma yapılamadı", "Sıcaklık ve basınç girilmelidir.");
      return;
    }
    setCompareError(null);
    compare.mutate(
      {
        temperature_c: inputs.pressure.temperature_c,
        pressure_bar: inputs.pressure.pressure_bar,
        steel_alpha_micro_per_c: inputs.helper.steel_alpha_micro_per_c,
        steel_model: inputs.modes.steel_model,
      },
      {
        onError: (error) => setCompareError(error.message),
      },
    );
  }

  function runBackendCompare() {
    if (inputs.pressure.temperature_c === null || inputs.pressure.pressure_bar === null) return;
    backendCompare.mutate({
      temperature_c: inputs.pressure.temperature_c,
      pressure_bar: inputs.pressure.pressure_bar,
    });
  }

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Katsayı Detayı"
        title="Üç kaynak, backend ve A onarım karşılaştırması"
        description="Kurum içi tablo, GAIL referansı ve otomatik β−3α aynı düğümde çözülür. A onarım bilgisi ham hücre ile onarılmış değeri yan yana gösterir."
        meta={
          <>
            <span className="chip">
              T {fmt.c(inputs.pressure.temperature_c)} · P {fmt.bar(inputs.pressure.pressure_bar)}
            </span>
            <span className="chip">{inputs.modes.steel_model}</span>
            <Badge tone={bCompare ? "pass" : "pending"}>
              {bCompare ? "karşılaştırma hazır" : "karşılaştırma bekliyor"}
            </Badge>
          </>
        }
        actions={
          <>
            <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => setTab("coefficients")}>
              Katsayılara dön
            </Button>
            <Button size="lg" variant="primary" icon={<RefreshCw size={15} />} loading={compare.isPending} onClick={runCompare}>
              Karşılaştır
            </Button>
          </>
        }
      />

      <SectionCard
        title="Üç kaynak karşılaştırması"
        description="Aynı T/P düğümünde kurum içi, GAIL ve otomatik B değerleri."
        icon={Table2}
        action={
          <Button size="sm" icon={<RefreshCw size={12} />} loading={compare.isPending} onClick={runCompare}>
            Karşılaştır
          </Button>
        }
      >
        {compareError ? <InlineNotice tone="danger" title="Karşılaştırma başarısız">{compareError}</InlineNotice> : null}
        {bCompare ? (
          <>
            <div className="table-wrap scroll-thin mt-1">
              <table className="data">
                <caption>
                  T = {fmt.c(bCompare.temperature_c)} · P = {fmt.bar(bCompare.pressure_bar)}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Kaynak</th>
                    <th scope="col" className="num">B (10⁻⁶/°C)</th>
                    <th scope="col" className="num">Kurum içi farkı</th>
                    <th scope="col">Durum</th>
                    <th scope="col">Not</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    { key: "institutional", row: bCompare.institutional },
                    { key: "gail", row: bCompare.gail },
                    { key: "auto", row: bCompare.auto },
                  ].map(({ key, row }) => {
                    const delta =
                      key === "institutional"
                        ? 0
                        : row.b_micro_per_c - bCompare.institutional.b_micro_per_c;
                    return (
                      <tr key={key} className={cn(key === inputs.modes.pressure_b_source && "bg-[var(--primary-soft)]")}>
                        <td>
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-[var(--text)]">{row.label}</span>
                            {key === inputs.modes.pressure_b_source ? <Badge tone="info">seçili</Badge> : null}
                          </div>
                        </td>
                        <td className="num">{num(row.b_micro_per_c, 6)}</td>
                        <td className={cn("num", delta === 0 ? "text-[var(--text-faint)]" : "tone-warning")}>
                          {delta === 0 ? "—" : `${delta > 0 ? "+" : ""}${num(delta, 6)}`}
                        </td>
                        <td>
                          {row.repaired_table ? <Badge tone="warning">onarıldı</Badge> : <Badge tone="pass">ham</Badge>}
                        </td>
                        <td className="max-w-[320px] text-[10.5px] leading-snug text-[var(--text-muted)]">
                          {row.note}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
              <ResultTile label="Kurum içi ↔ GAIL" value={num(bCompare.deltas.institutional_vs_gail, 6)} unit="10⁻⁶/°C" />
              <ResultTile label="Otomatik ↔ kurum içi" value={num(bCompare.deltas.auto_vs_institutional, 6)} unit="10⁻⁶/°C" />
              <ResultTile label="Otomatik ↔ GAIL" value={num(bCompare.deltas.auto_vs_gail, 6)} unit="10⁻⁶/°C" />
            </div>
          </>
        ) : (
          <p className="text-[11.5px] leading-relaxed text-[var(--text-faint)]">
            Henüz karşılaştırma yapılmadı. “Karşılaştır” üç kaynağı aynı düğümde çözer ve farkları
            gösterir.
          </p>
        )}
      </SectionCard>

      <div className="grid gap-4 xl:grid-cols-2">
        <SectionCard
          title="Backend karşılaştırması"
          description="Kurulu su özelliği backend'leri için A, β ve yoğunluk."
          icon={Database}
          action={
            <Button size="sm" icon={<RefreshCw size={12} />} loading={backendCompare.isPending} onClick={runBackendCompare}>
              Çalıştır
            </Button>
          }
        >
          {results.backendCompare ? (
            <div className="table-wrap scroll-thin">
              <table className="data">
                <caption>T = {fmt.c(results.backendCompare.temperature_c)} · P = {fmt.bar(results.backendCompare.pressure_bar)}</caption>
                <thead>
                  <tr>
                    <th scope="col">Backend</th>
                    <th scope="col" className="num">A</th>
                    <th scope="col" className="num">β</th>
                    <th scope="col" className="num">ρ (kg/m³)</th>
                  </tr>
                </thead>
                <tbody>
                  {results.backendCompare.items.map((item) => (
                    <tr key={item.backend.key}>
                      <td>
                        <span className="font-medium text-[var(--text)]">{item.backend.label}</span>
                        {!item.backend.distribution_ready ? (
                          <Badge tone="warning" className="ml-2">dağıtım dışı</Badge>
                        ) : null}
                      </td>
                      <td className="num">{num(item.a_micro_per_bar, 6)}</td>
                      <td className="num">{num(item.beta_micro_per_c, 6)}</td>
                      <td className="num">{num(item.density_kg_per_m3, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-[11.5px] leading-relaxed text-[var(--text-faint)]">
              Backend listesi meta uçtan gelir. Karşılaştırma, A değerinin backend’e göre değişimini
              gösterir.
            </p>
          )}
        </SectionCard>

        <SectionCard
          title="A onarım bilgisi"
          description="Kurum içi tablodaki 7 °C / 81–100 bar anomalisi çalışma zamanında onarılır."
          icon={Wrench}
          action={
            <Button
              size="sm"
              icon={<Table2 size={12} />}
              loading={tablePoint.isPending}
              onClick={() => tablePoint.mutate({ table: "institutional", temperature_c: 7, pressure_bar: 90 })}
            >
              7 °C / 90 bar örneği
            </Button>
          }
        >
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2.5">
              <p className="eyebrow">Kurum içi / BOTAŞ</p>
              <p className="mt-1 font-mono text-[11px] text-[var(--text-soft)]">
                {institutional
                  ? `${institutional.temperature.min}–${institutional.temperature.max} °C · ${institutional.pressure.min}–${institutional.pressure.max} bar`
                  : "—"}
              </p>
              <p className="mt-1 text-[10px] text-[var(--text-faint)]">
                {institutional?.source_note ?? "Kaynak bilgisi meta uçtan gelir."}
              </p>
            </div>
            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-2.5">
              <p className="eyebrow">GAIL</p>
              <p className="mt-1 font-mono text-[11px] text-[var(--text-soft)]">
                {gail ? `${gail.temperature.min}–${gail.temperature.max} °C · ${gail.pressure.min}–${gail.pressure.max} bar` : "—"}
              </p>
              <p className="mt-1 text-[10px] text-[var(--text-faint)]">
                {gail?.source_note ?? "Kaynak bilgisi meta uçtan gelir."}
              </p>
            </div>
          </div>

          {results.tablePoint ? (
            <div className="mt-3 rounded-lg border border-[var(--warning-border)] bg-[var(--warning-bg)] px-3 py-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={results.tablePoint.repaired ? "warning" : "pass"}>
                  {results.tablePoint.repaired ? "Onarılmış A" : "Ham hücre"}
                </Badge>
                <span className="font-mono text-[11px] text-[var(--text-soft)]">
                  T={num(results.tablePoint.requested.temperature_c, 1)} °C · P={num(results.tablePoint.requested.pressure_bar, 1)} bar
                </span>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <ResultTile label="A" value={num(results.tablePoint.a_micro_per_bar, 6)} unit="10⁻⁶/bar" />
                <ResultTile label="B" value={num(results.tablePoint.b_micro_per_c, 6)} unit="10⁻⁶/°C" />
              </div>
              {results.tablePoint.repair_note ? (
                <p className="mt-2 text-[10.5px] leading-relaxed text-[var(--text-muted)]">
                  {results.tablePoint.repair_note}
                </p>
              ) : null}
            </div>
          ) : (
            <p className="mt-3 text-[11px] leading-relaxed text-[var(--text-faint)]">
              “7 °C / 90 bar örneği” düğmesi onarım davranışını ve kaynak notunu gösterir. Resmi
              karar için onarılmış A değerinin denetim izi kontrol edilmelidir.
            </p>
          )}
        </SectionCard>
      </div>

      <InlineNotice tone="info" title="Provenance" icon={Info}>
        HESAP = backend hesabı, TABLO = referans hücre, MANUEL = kullanıcı değeri, BAYAT = girdi
        değiştiği için yenilenmesi gereken katsayı. Mod değişince eski değer temizlenir; yeni modun
        değeri yeniden üretilmelidir.
      </InlineNotice>

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-3.5 py-2.5">
        <p className="text-[10.5px] text-[var(--text-faint)]">
          Detay kararları ana katsayı sayfasındaki A/B değerlerini değiştirmez.
        </p>
        <Button size="sm" variant="ghost" icon={<Sigma size={12} />} onClick={() => setTab("coefficients")}>
          A/B hazırlığına dön
        </Button>
      </div>
    </div>
  );
}
