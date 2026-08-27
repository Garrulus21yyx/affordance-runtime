"use client";

import * as AlertDialog from "@radix-ui/react-alert-dialog";
import { Badge, Button, Card, Flex, Heading, Text, TextArea, Theme } from "@radix-ui/themes";
import { Activity, CircleOff, Eye, Hand, Pause, Play, Radio, RotateCcw, ShieldCheck, Square } from "lucide-react";
import { FormEvent, useState } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";
import { useShellSession } from "@/hooks/use-shell-session";
import type { ShellViewModel } from "@/session/view-model";

function PanelHeader({ eyebrow, title, state }: { eyebrow: string; title: string; state?: string }) {
  return (
    <header className="panel-header">
      <div><span className="eyebrow">{eyebrow}</span><Heading as="h2" size="4">{title}</Heading></div>
      {state && <Badge color={state === "live" ? "teal" : "gray"}>{state}</Badge>}
    </header>
  );
}

export function EffectReconciliationNotice({ view }: { view: ShellViewModel }) {
  const reconciliation = view.effectReconciliation;
  if (!reconciliation) return null;
  return (
    <Card className="reconciliation-card" data-testid="effect-reconciliation">
      <Text size="1" color={reconciliation.status === "compensated" ? "green" : "orange"}>EFFECT · {reconciliation.status}</Text>
      <Text as="p" size="3">{reconciliation.original_action} · {reconciliation.resource_ref}</Text>
      <Text as="p" size="1" color="gray">{reconciliation.code} · {reconciliation.reversibility}</Text>
    </Card>
  );
}

function Conversation({ view, submitMessage, revise, confirm }: {
  view: ShellViewModel;
  submitMessage: (message: string) => Promise<void>;
  revise: (message: string) => Promise<void>;
  confirm: (approved: boolean) => Promise<unknown>;
}) {
  const [message, setMessage] = useState("");
  const [revision, setRevision] = useState("");
  const submit = (handler: (value: string) => Promise<void>, clear: () => void) => async (event: FormEvent) => {
    event.preventDefault();
    const value = handler === revise ? revision.trim() : message.trim();
    if (!value) return;
    await handler(value);
    clear();
  };
  return (
    <section className="panel conversation" aria-label="Conversation">
      <PanelHeader eyebrow="Command channel" title="Conversation" state={view.runStatus} />
      {view.question && <Card className="pending-card" data-testid="pending-question"><Text size="1" color="orange">ASKUSER · {view.question.request_id}</Text><Text as="p" size="3">{view.question.prompt}</Text></Card>}
      {view.completion && <Card className="completion-card" data-testid="completion"><ShieldCheck size={16} /><Text weight="bold">{view.completion.outcome}</Text><Text as="p">{view.completion.message}</Text></Card>}
      <EffectReconciliationNotice view={view} />
      <form className="chat-frame" onSubmit={submit(submitMessage, () => setMessage(""))}>
        <TextArea aria-label="Task command" value={message} onChange={(event) => setMessage(event.target.value)} placeholder={view.composer.placeholder} disabled={!view.composer.enabled} />
        <Button type="submit" disabled={!view.composer.enabled || !message.trim()}>Send</Button>
      </form>
      {view.actions.revise && <form className="revision-form" onSubmit={submit(revise, () => setRevision(""))}><TextArea aria-label="Revise task" value={revision} onChange={(event) => setRevision(event.target.value)} placeholder="Revise the active task…" /><Button type="submit" disabled={!revision.trim()}>Revise task</Button></form>}
      <AlertDialog.Root open={Boolean(view.confirmation)}>
        <AlertDialog.Portal><AlertDialog.Overlay className="dialog-overlay" /><AlertDialog.Content className="dialog-content" data-testid="confirmation-dialog">
          <AlertDialog.Title>Runtime confirmation</AlertDialog.Title>
          <AlertDialog.Description>{view.confirmation?.summary} · risk: {view.confirmation?.risk}</AlertDialog.Description>
          <Flex gap="3" justify="end" mt="4"><AlertDialog.Cancel asChild><Button variant="soft" onClick={() => confirm(false)}>Reject action</Button></AlertDialog.Cancel><AlertDialog.Action asChild><Button color="orange" onClick={() => confirm(true)}>Approve action</Button></AlertDialog.Action></Flex>
        </AlertDialog.Content></AlertDialog.Portal>
      </AlertDialog.Root>
    </section>
  );
}

export function LiveView({ view }: { view: ShellViewModel }) {
  const surface = view.surface;
  return (
    <section className="panel surface" aria-label="Live surface">
      <PanelHeader eyebrow="Runtime surface" title="Live Surface" state={surface.status} />
      {surface.status !== "unavailable" ? <><div className="viewer-control-state" data-testid="surface-control-state"><Badge color={surface.interactive ? "orange" : "gray"}>{surface.interactive ? "user control" : "agent control · read-only"}</Badge></div><iframe key={surface.frameKey} title={surface.interactive ? "Interactive live surface" : "Read-only live surface"} src={surface.protectedPath} sandbox="allow-scripts allow-same-origin" /></> : <div className="viewer-unavailable" data-testid="surface-unavailable"><div className="viewer-reticle" aria-hidden="true"><CircleOff size={36} strokeWidth={1.3} /></div><span className="viewer-kicker"><Eye size={13} /> LIVE SURFACE / NO MEDIA ROUTE</span><Heading size="5">Surface unavailable</Heading><code>{surface.reasonCode}</code></div>}
    </section>
  );
}

export function Progress({ view }: { view: ShellViewModel }) {
  return <section className="panel progress" aria-label="Task progress"><PanelHeader eyebrow="Live progress" title="What’s happening" state={view.runStatus} /><div className="progress-summary"><span>Current task</span><strong>{view.taskText}</strong></div><ol className="progress-rail" aria-label="Runtime progress updates">{view.steps.map((step) => <li key={step.step}><span aria-hidden="true">{step.step.toString().padStart(2, "0")}</span><div><strong>{step.label}</strong><small>{step.status}</small></div></li>)}{!view.steps.length && <li className="empty"><span aria-hidden="true">00</span><div><strong>Ready when you are</strong><small>Progress will appear here</small></div></li>}</ol></section>;
}

export function ShellApp() {
  const shell = useShellSession();
  const view = shell.viewModel;
  return (
    <Theme accentColor="orange" grayColor="slate" radius="small"><main className="shell-main">
      <div className="topbar"><div className="wordmark"><Activity /><span>INTERACTION</span><strong>FLIGHT DECK</strong></div><div className="topology"><span>CONVERSATION</span><i /><span>LIVE SURFACE</span><i /><span>PROGRESS</span></div><div className="connection">
        {view.actions.returnControl && <Button size="1" variant="solid" color="orange" onClick={shell.returnControl}><RotateCcw size={11} /> Return to Agent</Button>}
        {view.actions.takeOver && <Button size="1" variant="soft" color="orange" onClick={shell.takeOver}><Hand size={11} /> Take control</Button>}
        {view.actions.resume && <Button size="1" variant="soft" color="teal" onClick={shell.resume}><Play size={11} /> Resume task</Button>}
        {view.actions.pause && <Button size="1" variant="soft" color="orange" onClick={shell.pause}><Pause size={11} /> Pause task</Button>}
        {view.actions.cancel && <Button size="1" variant="soft" color="red" onClick={shell.cancel}><Square size={11} /> Cancel task</Button>}
        <Radio size={14} /><span>{shell.connection}</span>
      </div></div>
      {shell.notice && <div className="notice" role="status">{shell.notice}</div>}
      <Group orientation="horizontal" className="shell-grid"><Panel defaultSize="29%" minSize="22%"><Conversation view={view} submitMessage={shell.submitMessage} revise={shell.revise} confirm={shell.confirm} /></Panel><Separator className="resize-handle" /><Panel defaultSize="42%" minSize="28%"><LiveView view={view} /></Panel><Separator className="resize-handle" /><Panel defaultSize="29%" minSize="23%"><Progress view={view} /></Panel></Group>
    </main></Theme>
  );
}
