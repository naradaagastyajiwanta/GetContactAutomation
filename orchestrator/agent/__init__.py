def __getattr__(name: str):
    if name == "ReactAgent":
        from orchestrator.agent.react_agent import ReactAgent
        return ReactAgent
    if name == "LearningSystem":
        from orchestrator.agent.learning import LearningSystem
        return LearningSystem
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ReactAgent", "LearningSystem"]
