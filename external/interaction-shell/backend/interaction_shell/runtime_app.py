"""Explicit production composition for the Core-owned public session port."""

from affordance_runtime.app.public_session import TargetRuntimeSessionFactory

from .api import create_app
from .core_runtime_port import CoreRuntimeSessionPort
from .manager import RunSessionManager


def create_runtime_app(factory: TargetRuntimeSessionFactory):
    """Build the Web API after deployment supplies Runtime and environment ownership."""

    return create_app(RunSessionManager(CoreRuntimeSessionPort(factory)))
