"use client";

import { CopilotChatView, CopilotKitProvider } from "@copilotkit/react-core/v2";
import * as AlertDialog from "@radix-ui/react-alert-dialog";
import { Badge, Button, Card, Flex, Heading, Text, Theme } from "@radix-ui/themes";
import {
  Activity,
  CircleOff,
  Eye,
  Hand,
  Pause,
  Play,
  Radio,
  RotateCcw,
  ShieldCheck,
  Square,
} from "lucide-react";
import { Group, Panel, Separator } from "react-resizable-panels";
import { useShellSession } from "@/hooks/use-shell-session";
import type { Snapshot } from "@/lib/types";

const HiddenSlot = () => null;

function PanelHeader({ eyebrow, title, state }: { eyebrow: string; title: string; state?: string }) {
  return (
    <header className="panel-header">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <Heading as="h2" size="4">{title}</Heading>
      </div>
      {state && <Badge color={state === "live" ? "teal" : "gray"}>{state}</Badge>}
    </header>
  );
}

export function EffectReconciliationNotice({ snapshot }: { snapshot: Snapshot | null }) {
  const reconciliation = snapshot?.effect_reconciliation;
  if (!reconciliation) return null;
  return (
    <Card className="reconciliation-card" data-testid="effect-reconciliation">
      <Text size="1" color={reconciliation.status === "compensated" ? "green" : "orange"}>
        EFFECT · {reconciliation.status}
      </Text>
      <Text as="p" size="3">
        {reconciliation.original_action} · {reconciliation.resource_ref}
      </Text>
      <Text as="p" size="1" color="gray">
        {reconciliation.code} · {reconciliation.reversibility}
      </Text>
    </Card>
  );
}

function Conversation({ snapshot, submitMessage, confirm }: {
  snapshot: Snapshot | null;
  submitMessage: (message: string) => Promise<void>;
  confirm: (approved: boolean) => Promise<void>;
}) {
  return (
    <section className="panel conversation" aria-label="Conversation">
      <PanelHeader eyebrow="Command channel" title="Conversation" state={snapshot?.run_status} />
      {snapshot?.pending_question && (
        <Card className="pending-card" data-testid="pending-question">
          <Text size="1" color="orange">ASKUSER · {snapshot.pending_question.request_id}</Text>
          <Text as="p" size="3">{snapshot.pending_question.prompt}</Text>
        </Card>
      )}
      {snapshot?.completion && (
        <Card className="completion-card" data-testid="completion">
          <ShieldCheck size={16} />
          <Text weight="bold">{snapshot.completion.outcome}</Text>
          <Text as="p">{snapshot.completion.message}</Text>
        </Card>
      )}
      <EffectReconciliationNotice snapshot={snapshot} />
      <div className="chat-frame">
        <CopilotChatView
          key={snapshot?.run_status ?? "opening"}
          messages={[]}
          isRunning={false}
          onSubmitMessage={submitMessage}
          welcomeScreen={false}
          disclaimer={HiddenSlot}
          input={{
            addMenuButton: HiddenSlot,
            textArea: {
              placeholder: snapshot?.run_status === "waiting_user"
                ? "Answer the question…"
                : snapshot?.control_owner === "user"
                  ? "Manual browser control is active…"
                : snapshot?.capabilities.includes("revise_task")
                  ? "Revise the current task…"
                  : "Describe a task…",
            },
            toolsMenu: [],
          }}
        />
      </div>
      <AlertDialog.Root open={Boolean(snapshot?.pending_confirmation)}>
        <AlertDialog.Portal>
          <AlertDialog.Overlay className="dialog-overlay" />
          <AlertDialog.Content className="dialog-content" data-testid="confirmation-dialog">
            <AlertDialog.Title>Runtime confirmation</AlertDialog.Title>
            <AlertDialog.Description>
              {snapshot?.pending_confirmation?.summary} · risk: {snapshot?.pending_confirmation?.risk}
            </AlertDialog.Description>
            <Flex gap="3" justify="end" mt="4">
              <AlertDialog.Cancel asChild><Button variant="soft" onClick={() => confirm(false)}>Reject action</Button></AlertDialog.Cancel>
              <AlertDialog.Action asChild><Button color="orange" onClick={() => confirm(true)}>Approve action</Button></AlertDialog.Action>
            </Flex>
          </AlertDialog.Content>
        </AlertDialog.Portal>
      </AlertDialog.Root>
    </section>
  );
}

export function LiveView({ snapshot }: { snapshot: Snapshot | null }) {
  const viewer = snapshot?.viewer;
  const interactive = snapshot?.control_owner === "user" && viewer?.read_only === false;
  return (
    <section className="panel surface" aria-label="Browser live view">
      <PanelHeader eyebrow="Browser session" title="Browser Live View" state={viewer?.status ?? "unavailable"} />
      {viewer?.status === "available" && viewer.protected_path ? (
        <>
          <div className="viewer-control-state" data-testid="viewer-control-state">
            <Badge color={interactive ? "orange" : "gray"}>
              {interactive ? "user control" : "agent control · read-only"}
            </Badge>
          </div>
          <iframe
            key={`${viewer.protected_path}:${interactive ? "interactive" : "read-only"}`}
            title={interactive ? "Interactive browser live view" : "Read-only browser live view"}
            src={viewer.protected_path}
            sandbox="allow-scripts allow-same-origin"
          />
        </>
      ) : (
        <div className="viewer-unavailable" data-testid="viewer-unavailable">
          <div className="viewer-reticle" aria-hidden="true"><CircleOff size={36} strokeWidth={1.3} /></div>
          <span className="viewer-kicker"><Eye size={13} /> LIVE SURFACE / NO MEDIA ROUTE</span>
          <Heading size="5">Viewer unavailable</Heading>
          <code>{viewer?.reason_code ?? "viewer_not_configured"}</code>
          <Badge color="gray">read-only · takeover unsupported</Badge>
          <div className="viewer-readout"><span>provider</span><strong>not configured</strong><span>control lease</span><strong>unavailable</strong></div>
        </div>
      )}
    </section>
  );
}

export function Progress({ snapshot }: { snapshot: Snapshot | null }) {
  const steps = snapshot?.public_steps ?? [];
  return (
    <section className="panel progress" aria-label="Task progress">
      <PanelHeader eyebrow="Live progress" title="What’s happening" state={snapshot?.run_status} />
      <div className="progress-summary">
        <span>Current task</span>
        <strong>{snapshot?.task_text ?? "Waiting for a task"}</strong>
      </div>
      <ol className="progress-rail" aria-label="Runtime progress updates">
        {steps.map((step) => (
          <li key={step.step}>
            <span aria-hidden="true">{step.step.toString().padStart(2, "0")}</span>
            <div><strong>{step.label}</strong><small>{step.status}</small></div>
          </li>
        ))}
        {!steps.length && <li className="empty"><span aria-hidden="true">00</span><div><strong>Ready when you are</strong><small>Progress will appear here</small></div></li>}
      </ol>
    </section>
  );
}

export function ShellApp() {
  const shell = useShellSession();
  const pausable = Boolean(
    shell.snapshot?.capabilities.includes("pause_task")
    && ["running", "waiting_user", "waiting_confirmation"].includes(shell.snapshot.run_status),
  );
  const cancellable = Boolean(
    shell.snapshot?.capabilities.includes("cancel_task")
    && ["running", "waiting_user", "waiting_confirmation"].includes(shell.snapshot.run_status),
  );
  const resumable = Boolean(
    shell.snapshot?.capabilities.includes("resume_task")
    && shell.snapshot.run_status === "paused"
    && shell.snapshot.resume_eligible
    && shell.snapshot.checkpoint_id,
  );
  const takeoverAvailable = Boolean(
    shell.snapshot?.capabilities.includes("take_over")
    && shell.snapshot.run_status === "paused"
    && shell.snapshot.checkpoint_id
    && shell.snapshot.viewer.status === "available",
  );
  const userControlled = Boolean(
    shell.snapshot?.capabilities.includes("return_control")
    && shell.snapshot.control_owner === "user"
    && shell.snapshot.control_lease_id,
  );
  return (
    <CopilotKitProvider runtimeUrl="/api/copilotkit">
      <Theme accentColor="orange" grayColor="slate" radius="small">
        <main className="shell-main">
          <div className="topbar">
            <div className="wordmark"><Activity /><span>INTERACTION</span><strong>FLIGHT DECK</strong></div>
            <div className="topology"><span>CONVERSATION</span><i /><span>LIVE VIEW</span><i /><span>PROGRESS</span></div>
            <div className="connection">
              {userControlled && (
                <Button size="1" variant="solid" color="orange" onClick={shell.returnControl}>
                  <RotateCcw size={11} /> Return to Agent
                </Button>
              )}
              {takeoverAvailable && (
                <Button size="1" variant="soft" color="orange" onClick={shell.takeOver}>
                  <Hand size={11} /> Take control
                </Button>
              )}
              {resumable && (
                <Button size="1" variant="soft" color="teal" onClick={shell.resume}>
                  <Play size={11} /> Resume task
                </Button>
              )}
              {pausable && (
                <Button size="1" variant="soft" color="orange" onClick={shell.pause}>
                  <Pause size={11} /> Pause task
                </Button>
              )}
              {cancellable && (
                <Button size="1" variant="soft" color="red" onClick={shell.cancel}>
                  <Square size={11} /> Cancel task
                </Button>
              )}
              <Radio size={14} /><span>{shell.connection}</span>
            </div>
          </div>
          {shell.notice && <div className="notice" role="status">{shell.notice}</div>}
          <Group orientation="horizontal" className="shell-grid">
            <Panel defaultSize="29%" minSize="22%"><Conversation snapshot={shell.snapshot} submitMessage={shell.submitMessage} confirm={shell.confirm} /></Panel>
            <Separator className="resize-handle" />
            <Panel defaultSize="42%" minSize="28%"><LiveView snapshot={shell.snapshot} /></Panel>
            <Separator className="resize-handle" />
            <Panel defaultSize="29%" minSize="23%"><Progress snapshot={shell.snapshot} /></Panel>
          </Group>
        </main>
      </Theme>
    </CopilotKitProvider>
  );
}
