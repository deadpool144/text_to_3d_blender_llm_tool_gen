import os
from typing import Optional
from src.llm.llm_model import get_gemini_model

PROMPT_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "prompts", "description_prompt.md")
)


def load_describer_prompt() -> str:
    """Load the description expander system prompt from markdown file."""
    if os.path.exists(PROMPT_FILE):
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return (
        "You are an expert 3D Concept Designer. Expand user prompts into detailed 3D part breakdowns "
        "including dimensions, subcomponents, materials, and geometry shapes."
    )


def expand_user_prompt(user_input: str, temperature: float = 0.5) -> str:
    """Layer 1 AI: Takes simple user text and expands it into a comprehensive 3D technical breakdown.

    Args:
        user_input: Raw human description (e.g., 'a wooden chair').
        temperature: Sampling temperature for creative/technical expansion.

    Returns:
        Detailed 3D description text for the next generation stage.
    """
    system_prompt = load_describer_prompt()
    llm = get_gemini_model(temperature=temperature)

    messages = [
        ("system", system_prompt),
        (
            "human",
            f"Expand the following 3D object concept into a comprehensive, detailed breakdown of all parts, "
            f"dimensions, geometric primitives, and materials:\n\n\"{user_input.strip()}\"",
        ),
    ]

    response = llm.invoke(messages)
    expanded_text = response.content
    return expanded_text.strip() if isinstance(expanded_text, str) else str(expanded_text)
