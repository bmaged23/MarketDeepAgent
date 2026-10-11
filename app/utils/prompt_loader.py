from pathlib import Path


def load_prompt(agent_name, filename="system.md"):
    root = Path(__file__).resolve().parents[1] / "agents"
    path = (root / agent_name / "prompts" / filename).resolve()
    if not path.is_relative_to(root.resolve()) or path.suffix != ".md":
        raise ValueError("Invalid prompt path")
    return path.read_text(encoding="utf-8")
