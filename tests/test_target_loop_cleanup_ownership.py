import pytest

from affordance_runtime.benchmarks.target_loop.real_adapter_support import require_thread_stopped


class FakeThread:
    def __init__(self, alive: bool) -> None:
        self.alive = alive

    def join(self, timeout: float) -> None:
        del timeout

    def is_alive(self) -> bool:
        return self.alive


def test_cleanup_rejects_live_owner_thread() -> None:
    with pytest.raises(RuntimeError, match="owner thread"):
        require_thread_stopped(FakeThread(True), timeout=0.01)


def test_cleanup_accepts_stopped_owner_thread() -> None:
    require_thread_stopped(FakeThread(False), timeout=0.01)
