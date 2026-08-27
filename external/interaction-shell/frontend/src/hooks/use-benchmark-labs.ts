"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { parse } from "valibot";
import {
  getCurrentLabRun,
  getLabConfiguration,
  getLabRunActivity,
  getLabRunBrowserFrame,
  getLabRunEvents,
  listCompletedRuns,
  listLabRuns,
  startLabRun,
  stopLabRun,
} from "@/generated/sdk.gen";
import type {
  BenchmarkLabConfiguration,
  BenchmarkLabRunSpec,
  BenchmarkLabRunSummary,
  CompletedRunSummary,
} from "@/generated/types.gen";
import {
  vGetCurrentLabRunResponse,
  vGetLabConfigurationResponse,
  vGetLabRunActivityResponse,
  vGetLabRunEventsResponse,
  vListCompletedRunsResponse,
  vListLabRunsResponse,
  vStartLabRunResponse,
  vStopLabRunResponse,
} from "@/generated/valibot.gen";
import { shellClient } from "@/session/client";

export type LabEvent = Record<string, unknown>;

export function useBenchmarkLabs(enabled: boolean) {
  const [configuration, setConfiguration] = useState<BenchmarkLabConfiguration | null>(null);
  const [runs, setRuns] = useState<BenchmarkLabRunSummary[]>([]);
  const [completedRuns, setCompletedRuns] = useState<CompletedRunSummary[]>([]);
  const [selectedRun, setSelectedRun] = useState<BenchmarkLabRunSummary | null>(null);
  const [activity, setActivity] = useState<LabEvent[]>([]);
  const [rawEvents, setRawEvents] = useState<LabEvent[]>([]);
  const [frameUrl, setFrameUrl] = useState("");
  const [state, setState] = useState<"idle" | "loading" | "ready" | "unavailable">("idle");
  const [error, setError] = useState("");
  const selectedRef = useRef<BenchmarkLabRunSummary | null>(null);
  const activityCursor = useRef(0);
  const rawCursor = useRef(0);
  const polling = useRef(false);
  const loadStarted = useRef(false);
  const frameObjectUrl = useRef("");

  const installSelected = useCallback((run: BenchmarkLabRunSummary | null) => {
    const changed = selectedRef.current?.run_id !== run?.run_id;
    selectedRef.current = run;
    setSelectedRun(run);
    if (changed) {
      activityCursor.current = 0;
      rawCursor.current = 0;
      setActivity([]);
      setRawEvents([]);
      if (frameObjectUrl.current) URL.revokeObjectURL(frameObjectUrl.current);
      frameObjectUrl.current = "";
      setFrameUrl("");
    }
  }, []);

  const refreshCollections = useCallback(async () => {
    const [configResponse, runsResponse, currentResponse, completedResponse] = await Promise.all([
      getLabConfiguration({ client: shellClient, throwOnError: true }),
      listLabRuns({ client: shellClient, throwOnError: true }),
      getCurrentLabRun({ client: shellClient, throwOnError: true }),
      listCompletedRuns({ client: shellClient, throwOnError: true }),
    ]);
    const config = parse(vGetLabConfigurationResponse, configResponse.data);
    const listed = parse(vListLabRunsResponse, runsResponse.data);
    const current = parse(vGetCurrentLabRunResponse, currentResponse.data);
    const completed = parse(vListCompletedRunsResponse, completedResponse.data);
    setConfiguration(config);
    setRuns(listed.runs);
    setCompletedRuns(completed);
    if (!selectedRef.current && current) installSelected(current);
  }, [installSelected]);

  useEffect(() => {
    if (!enabled || loadStarted.current) return;
    loadStarted.current = true;
    let active = true;
    const load = async () => {
      setState("loading");
      try {
        await refreshCollections();
        if (!active) return;
        setState("ready");
        setError("");
      } catch (reason: unknown) {
        if (!active) return;
        setState("unavailable");
        setError(reason instanceof Error ? reason.message : "Labs unavailable");
      }
    };
    void load();
    return () => { active = false; };
  }, [enabled, refreshCollections]);

  const refreshFrame = useCallback(async (runId: string) => {
    try {
      const response = await getLabRunBrowserFrame({
        client: shellClient,
        path: { run_id: runId },
        parseAs: "blob",
        throwOnError: true,
      });
      if (!(response.data instanceof Blob) || selectedRef.current?.run_id !== runId) return;
      const next = URL.createObjectURL(response.data);
      if (frameObjectUrl.current) URL.revokeObjectURL(frameObjectUrl.current);
      frameObjectUrl.current = next;
      setFrameUrl(next);
    } catch {
      // A frame is optional until Runtime records its first screenshot.
    }
  }, []);

  const poll = useCallback(async () => {
    const selected = selectedRef.current;
    if (!selected || polling.current) return;
    polling.current = true;
    try {
      const [activityResponse, eventsResponse] = await Promise.all([
        getLabRunActivity({
          client: shellClient,
          path: { run_id: selected.run_id },
          query: { after: activityCursor.current },
          throwOnError: true,
        }),
        getLabRunEvents({
          client: shellClient,
          path: { run_id: selected.run_id },
          query: { after: rawCursor.current },
          throwOnError: true,
        }),
      ]);
      const activityPage = parse(vGetLabRunActivityResponse, activityResponse.data);
      const rawPage = parse(vGetLabRunEventsResponse, eventsResponse.data);
      if (selectedRef.current?.run_id !== selected.run_id) return;
      activityCursor.current = activityPage.next_cursor;
      rawCursor.current = rawPage.next_cursor;
      setActivity((items) => [...items, ...activityPage.events]);
      setRawEvents((items) => [...items, ...rawPage.events]);
      selectedRef.current = activityPage.run;
      setSelectedRun(activityPage.run);
      setRuns((items) => items.map((item) => item.run_id === activityPage.run.run_id ? activityPage.run : item));
      if (activityPage.events.some((event) => event.event === "observation" && event.browser_frame_available === true)) {
        await refreshFrame(selected.run_id);
      }
      if (activityPage.run.status !== "running") await refreshCollections();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Unable to read Labs activity");
    } finally {
      polling.current = false;
    }
  }, [refreshCollections, refreshFrame]);

  useEffect(() => {
    if (!enabled || !selectedRun) return;
    void poll();
    if (selectedRun.status !== "running") return;
    const interval = window.setInterval(() => void poll(), 700);
    return () => window.clearInterval(interval);
  }, [enabled, poll, selectedRun]);

  useEffect(() => () => {
    if (frameObjectUrl.current) URL.revokeObjectURL(frameObjectUrl.current);
  }, []);

  const start = useCallback(async (spec: BenchmarkLabRunSpec) => {
    const response = await startLabRun({
      client: shellClient,
      body: spec,
      throwOnError: true,
    });
    const run = parse(vStartLabRunResponse, response.data);
    setRuns((items) => [run, ...items.filter((item) => item.run_id !== run.run_id)]);
    installSelected(run);
    setError("");
    return run;
  }, [installSelected]);

  const stop = useCallback(async () => {
    const run = selectedRef.current;
    if (!run) return;
    const response = await stopLabRun({
      client: shellClient,
      path: { run_id: run.run_id },
      throwOnError: true,
    });
    installSelected(parse(vStopLabRunResponse, response.data));
    await poll();
  }, [installSelected, poll]);

  return {
    configuration,
    runs,
    completedRuns,
    selectedRun,
    activity,
    rawEvents,
    frameUrl,
    state,
    error,
    selectRun: installSelected,
    refreshCollections,
    start,
    stop,
  };
}
