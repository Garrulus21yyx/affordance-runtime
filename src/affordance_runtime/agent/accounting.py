"""Single run-scoped authority for absolute physical attempt totals."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.agent.attempt_receipt import AttemptReceipt


@dataclass(frozen=True)
class RunAccountingSnapshot:
    observation_attempts: int
    execution_attempts: int
    effectful_dispatches: int
    currentness_probes: int
    waited_ms: int
    receipt_count: int


@dataclass
class RunAccounting:
    _observation_attempts: int = field(default=0, init=False, repr=False)
    _execution_attempts: int = field(default=0, init=False, repr=False)
    _effectful_dispatches: int = field(default=0, init=False, repr=False)
    _currentness_probes: int = field(default=0, init=False, repr=False)
    _waited_ms: int = field(default=0, init=False, repr=False)
    _receipt_ids: set[str] = field(default_factory=set, repr=False)

    def record(self, receipt: AttemptReceipt) -> None:
        if receipt.attempt_id in self._receipt_ids:
            raise ValueError("attempt receipt was already accounted")
        if receipt.attempt_id != self.next_attempt_id():
            raise ValueError("attempt receipt identity is not the next run-scoped sequence")
        self._receipt_ids.add(receipt.attempt_id)
        self._observation_attempts += receipt.acquisition_attempts
        self._execution_attempts += receipt.execution_attempts
        self._effectful_dispatches += receipt.effectful_dispatches
        self._currentness_probes += receipt.currentness_probe_count

    def record_wait(self, waited_ms: int) -> None:
        if type(waited_ms) is not int or waited_ms < 0:
            raise ValueError("wait accounting requires non-negative milliseconds")
        self._waited_ms += waited_ms

    @property
    def observation_attempts(self) -> int:
        return self._observation_attempts

    @property
    def execution_attempts(self) -> int:
        return self._execution_attempts

    @property
    def effectful_dispatches(self) -> int:
        return self._effectful_dispatches

    @property
    def currentness_probes(self) -> int:
        return self._currentness_probes

    @property
    def waited_ms(self) -> int:
        return self._waited_ms

    def next_attempt_id(self) -> str:
        return f"attempt:{self.receipt_count + 1}"

    @property
    def receipt_count(self) -> int:
        return len(self._receipt_ids)

    def snapshot(self) -> RunAccountingSnapshot:
        return RunAccountingSnapshot(
            self.observation_attempts,
            self.execution_attempts,
            self.effectful_dispatches,
            self.currentness_probes,
            self.waited_ms,
            self.receipt_count,
        )
