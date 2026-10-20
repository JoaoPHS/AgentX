"""Pick a model for a role and a key scope."""

from __future__ import annotations

from dataclasses import dataclass, field

from agentx.config import AppConfig
from agentx.errors import AgentXError

ROLES = ("orchestrator", "subagent", "main")


@dataclass
class Session:
    provider: str | None = None
    scope: str | None = None
    history: list[dict] = field(default_factory=list)

    def scope_name(self, config: AppConfig) -> str:
        return self.scope or config.routing.remote_scope

    def provider_name(self, config: AppConfig) -> str:
        if self.scope_name(config) == "local":
            return "local"
        if self.provider in (None, "local"):
            return config.routing.remote_provider
        return self.provider


def role_uses_remote(scope: str, role: str) -> bool:
    if scope == "all":
        return True
    if scope == "orchestrator":
        return role == "orchestrator"
    if scope == "main":
        return role == "main"
    return False


def scope_needs_local(scope: str) -> bool:
    """Local, orchestrator, and main still run at least one role on the phone."""
    return scope != "all"


def token_budget(router, role: str, local_cap: int) -> int | None:
    """None means the remote provider cap. Tight role caps still pass a number."""
    uses = getattr(router, "uses_remote", None)
    if callable(uses) and uses(role):
        return None
    return local_cap


class Router:
    def __init__(self, config: AppConfig, session: Session, governor, local, remote) -> None:
        self.config = config
        self.session = session
        self.governor = governor
        self.local = local
        self.remote = remote

    def scope(self) -> str:
        return self.session.scope_name(self.config)

    def uses_remote(self, role: str) -> bool:
        return role_uses_remote(self.scope(), role)

    def block_reason(self, role: str) -> str | None:
        if self.uses_remote(role):
            return self.remote.block_reason()
        return self.local.possible()

    def workers_ready(self) -> bool:
        if not scope_needs_local(self.scope()):
            return True
        return self.local.possible() is None

    def complete(
        self,
        role: str,
        messages: list[dict],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.2,
        timeout: float = 180,
        on_token=None,
    ) -> str:
        reason = self.block_reason(role)
        if reason:
            raise AgentXError(reason)
        if self.uses_remote(role):
            with self.governor.lock:
                return self.remote.complete(
                    messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=timeout,
                    on_token=on_token,
                )
        local_cap = 256 if max_tokens is None else max_tokens
        with self.governor.lock:
            self.local.ensure_running()
            return self.local.complete(
                messages,
                max_tokens=local_cap,
                temperature=temperature,
                timeout=timeout,
                on_token=on_token,
            )
