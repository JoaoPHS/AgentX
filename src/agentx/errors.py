class AgentXError(Exception):
    """Error that can be shown to the user. The text follows the saved language."""

    def __str__(self) -> str:
        from agentx.i18n import t

        raw = self.args[0] if self.args else ""
        if not isinstance(raw, str):
            raw = str(raw)
        return t(raw)
