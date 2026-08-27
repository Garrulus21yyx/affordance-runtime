"use client";

import { Badge, Card, Flex, Heading, Text, Theme } from "@radix-ui/themes";
import { Activity, AlertTriangle, Database, ExternalLink, FileJson, Radio } from "lucide-react";
import { useEffect, useState } from "react";
import { parse } from "valibot";
import { createClient } from "@/generated/client";
import { listCompletedRuns } from "@/generated/sdk.gen";
import { vListCompletedRunsResponse } from "@/generated/valibot.gen";
import type { CompletedRunSummary } from "@/session/types";

const diagnosticsClient = createClient({ baseUrl: "/shell-api" });

function CaseDetail({ summary }: { summary: CompletedRunSummary }) {
  return (
    <Card className="diagnosis-detail" data-testid="completed-run-summary">
      <Flex align="center" justify="between" gap="3">
        <div>
          <span className="eyebrow">Authoritative completed case</span>
          <Heading size="6">{summary.case_id}</Heading>
        </div>
        <Badge color={summary.status === "done" ? "green" : "orange"}>{summary.status}</Badge>
      </Flex>
      <div className="diagnosis-grid">
        <span>benchmark result<strong>{summary.benchmark_result}</strong></span>
        <span>turns<strong>{summary.turns}</strong></span>
        <span>recoveries<strong>{summary.recoveries}</strong></span>
        <span>detour<strong>{summary.detour_disposition}</strong></span>
      </div>
      <div className="metric-strip">
        <span>provider input<strong>{summary.provider_input_tokens}</strong></span>
        <span>provider output<strong>{summary.provider_output_tokens}</strong></span>
        <span>stall / cycle<strong>{summary.control_stalls} / {summary.state_oscillations}</strong></span>
      </div>
      <div className="evidence-block">
        <span className="eyebrow">Open owner-backed evidence</span>
        <code>{summary.run_attempt_id}</code>
        <Flex gap="3" wrap="wrap">
          {summary.langfuse_url ? <a href={summary.langfuse_url} target="_blank" rel="noreferrer"><ExternalLink size={14} /> Open in Langfuse</a> : <Text color="gray">Langfuse unavailable</Text>}
          {summary.local_evidence_url ? <a href={`/shell-api${summary.local_evidence_url}`} target="_blank" rel="noreferrer"><FileJson size={14} /> Local result</a> : <Text color="gray">Local evidence unavailable</Text>}
        </Flex>
      </div>
    </Card>
  );
}

export function DiagnosticsWorkbench() {
  const [summaries, setSummaries] = useState<CompletedRunSummary[]>([]);
  const [selected, setSelected] = useState(0);
  const [state, setState] = useState<"loading" | "ready" | "unavailable">("loading");

  useEffect(() => {
    listCompletedRuns({ client: diagnosticsClient, throwOnError: true }).then((response) => {
      setSummaries(parse(vListCompletedRunsResponse, response.data));
      setState("ready");
    }).catch(() => setState("unavailable"));
  }, []);

  return (
    <Theme accentColor="orange" grayColor="slate" radius="small">
      <main className="diagnostics-workbench">
        <div className="topbar">
          <div className="wordmark"><Activity /><span>BAD CASE</span><strong>DIAGNOSTICS LAB</strong></div>
          <div className="topology"><span>BENCHMARK EXPORT</span><i /><span>PROJECTOR</span><i /><span>EVIDENCE</span></div>
          <div className="connection"><Radio size={14} /><span>{state}</span><code>{summaries.length} cases</code></div>
        </div>
        <header className="diagnostics-intro">
          <div>
            <span className="eyebrow">Engineering surface · not operator UI</span>
            <Heading size="8">One result. One analysis trail.</Heading>
          </div>
          <Text>Benchmark results remain authoritative. Full token, cost, latency, trace, and annotation analysis opens in Langfuse.</Text>
        </header>
        <div className="diagnostics-layout">
          <aside className="case-index">
            <div className="case-index-header"><Database size={16} /><strong>Exported cases</strong></div>
            {summaries.map((item, index) => (
              <button className={selected === index ? "selected" : ""} key={item.case_id} onClick={() => setSelected(index)}>
                <span>{item.case_id}</span><code>{item.status} / {item.detour_disposition}</code>
              </button>
            ))}
            {state === "ready" && !summaries.length && <div className="diagnostics-empty"><AlertTriangle size={18} />No configured completed runs.</div>}
            {state === "unavailable" && <div className="diagnostics-empty"><AlertTriangle size={18} />Completed-run summary unavailable.</div>}
          </aside>
          <section className="diagnostics-canvas">
            {summaries[selected] ? <CaseDetail summary={summaries[selected]} /> : <div className="diagnostics-placeholder">Select a completed case to open its analysis or evidence.</div>}
          </section>
        </div>
      </main>
    </Theme>
  );
}
