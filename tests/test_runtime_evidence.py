from affordance_runtime.runtime_evidence import semantic_progress_fingerprint
from affordance_runtime.state_kernel import StateKernel


def test_semantic_progress_fingerprint_ignores_legacy_pending_obligations() -> None:
    state = StateKernel(task_id="task", goal="Do it")
    before = semantic_progress_fingerprint(state)

    state.pending_obligations = ["legacy:string-obligation"]  # type: ignore[attr-defined]

    assert semantic_progress_fingerprint(state) == before
