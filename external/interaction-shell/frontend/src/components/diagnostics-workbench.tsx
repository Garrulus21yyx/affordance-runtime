"use client";

import { Badge, Card, Flex, Heading, Text, Theme } from "@radix-ui/themes";
import { Activity, AlertTriangle, Database, Radio } from "lucide-react";
import { useEffect, useState } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { listDiagnoses } from "@/lib/api";
import type { Diagnosis } from "@/lib/types";

function CaseDetail({ diagnosis }: { diagnosis: Diagnosis }) {
  const metrics = [
    { name: "attempts", value: diagnosis.trajectory_metrics.provider_attempts },
    { name: "retries", value: diagnosis.trajectory_metrics.retries },
    { name: "recovery", value: diagnosis.trajectory_metrics.recoveries },
  ];

  return (
    <Card className="diagnosis-detail" data-testid="diagnosis">
      <Flex align="center" justify="between" gap="3">
        <div>
          <span className="eyebrow">Selected exported case</span>
          <Heading size="6">{diagnosis.case_id}</Heading>
        </div>
        <Badge color="orange">{diagnosis.terminal_code}</Badge>
      </Flex>
      <div className="diagnosis-grid">
        <span>owner terminal stage<strong>{diagnosis.terminal_stage}</strong></span>
        <span>first abnormal step<strong>{diagnosis.first_abnormal_step ?? "unknown"}</strong></span>
        <span>likely upstream stage<strong>{diagnosis.likely_upstream_stage}</strong></span>
        <span>context health<strong>{diagnosis.context_health.classification}</strong></span>
      </div>
      <div className="diagnosis-chart" aria-label="Trajectory metrics">
        <ResponsiveContainer width="100%" height={210}>
          <BarChart data={metrics} margin={{ top: 22, right: 14, left: 14, bottom: 0 }}>
            <XAxis dataKey="name" tickLine={false} axisLine={false} />
            <Tooltip cursor={{ fill: "#E8EDF1" }} />
            <Bar dataKey="value" fill="#E9893A" radius={[2, 2, 0, 0]} minPointSize={5} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="metric-strip">
        <span>tokens<strong>{diagnosis.trajectory_metrics.prompt_tokens + diagnosis.trajectory_metrics.completion_tokens}</strong></span>
        <span>model latency<strong>{diagnosis.trajectory_metrics.model_latency_ms} ms</strong></span>
        <span>runtime latency<strong>{diagnosis.trajectory_metrics.runtime_latency_ms} ms</strong></span>
      </div>
      <div className="evidence-block">
        <span className="eyebrow">Evidence references</span>
        {diagnosis.evidence_refs.length ? diagnosis.evidence_refs.map((ref) => <code key={ref}>{ref}</code>) : <Text color="gray">No exported evidence reference.</Text>}
      </div>
    </Card>
  );
}

export function DiagnosticsWorkbench() {
  const [diagnoses, setDiagnoses] = useState<Diagnosis[]>([]);
  const [selected, setSelected] = useState(0);
  const [state, setState] = useState<"loading" | "ready" | "unavailable">("loading");

  useEffect(() => {
    listDiagnoses().then((items) => {
      setDiagnoses(items);
      setState("ready");
    }).catch(() => setState("unavailable"));
  }, []);

  return (
    <Theme accentColor="orange" grayColor="slate" radius="small">
      <main className="diagnostics-workbench">
        <div className="topbar">
          <div className="wordmark"><Activity /><span>BAD CASE</span><strong>DIAGNOSTICS LAB</strong></div>
          <div className="topology"><span>BENCHMARK EXPORT</span><i /><span>PROJECTOR</span><i /><span>EVIDENCE</span></div>
          <div className="connection"><Radio size={14} /><span>{state}</span><code>{diagnoses.length} cases</code></div>
        </div>
        <header className="diagnostics-intro">
          <div>
            <span className="eyebrow">Engineering surface · not operator UI</span>
            <Heading size="8">Failure attribution, with authority intact.</Heading>
          </div>
          <Text>This workbench consumes versioned benchmark results and public trace exports. Likely stage remains non-authoritative.</Text>
        </header>
        <div className="diagnostics-layout">
          <aside className="case-index">
            <div className="case-index-header"><Database size={16} /><strong>Exported cases</strong></div>
            {diagnoses.map((item, index) => (
              <button className={selected === index ? "selected" : ""} key={item.case_id} onClick={() => setSelected(index)}>
                <span>{item.case_id}</span><code>{item.terminal_stage} / {item.terminal_code}</code>
              </button>
            ))}
            {state === "ready" && !diagnoses.length && <div className="diagnostics-empty"><AlertTriangle size={18} />No projected cases loaded.</div>}
            {state === "unavailable" && <div className="diagnostics-empty"><AlertTriangle size={18} />Diagnostic export unavailable.</div>}
          </aside>
          <section className="diagnostics-canvas">
            {diagnoses[selected] ? <CaseDetail diagnosis={diagnoses[selected]} /> : <div className="diagnostics-placeholder">Select an exported case to inspect its deterministic projection.</div>}
          </section>
        </div>
      </main>
    </Theme>
  );
}
