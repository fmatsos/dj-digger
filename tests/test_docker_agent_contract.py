from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_docker_agent_config_uses_explicit_model_routing() -> None:
    text = (ROOT / "docker-agent.yaml").read_text()

    assert text.startswith("version: 15\n")
    assert (
        "luna_low:\n    provider: chatgpt\n    model: gpt-5.6-luna\n"
        "    thinking_budget: low" in text
    )
    assert (
        "sol_medium:\n    provider: chatgpt\n    model: gpt-5.6-sol\n"
        "    thinking_budget: medium" in text
    )
    assert "provider: openai" not in text
    assert "gpt-5-mini" not in text
    assert "lead:\n    model: luna_low" in text
    codex_section = text.split("  codex-worker:", 1)[1].split("  reviewer:", 1)[0]
    assert "harness:\n      type: codex\n      model: gpt-5.6-luna" in codex_section
    assert "reviewer:\n    model: sol_medium" in text


def test_model_routing_documentation_matches_configuration() -> None:
    agents = (ROOT / "AGENTS.md").read_text()
    guide = (ROOT / "docs/docker-agent-development.md").read_text()

    assert "GPT-5.6 Sol | medium" in agents
    assert "GPT-5.6 Luna | low" in agents
    assert "GPT-5.6 Luna | medium" in agents
    assert "gpt-5.6-luna" in guide
    assert "gpt-5.6-sol" in guide
