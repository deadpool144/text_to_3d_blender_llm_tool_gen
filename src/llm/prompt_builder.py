import os
from typing import Optional, List
from langchain_core.documents import Document

SYSTEM_PROMPT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "prompts", "system_prompt.md")
)


def load_system_prompt() -> str:
    """Read the system prompt markdown file."""
    if os.path.exists(SYSTEM_PROMPT_PATH):
        with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return "You are an expert 3D model generator. Output pure valid JSON for Universal 3D Model Spec v1.0.0."


def build_generation_prompt(user_description: str, retrieved_docs: Optional[List[Document]] = None) -> List[tuple]:
    """Combine system prompt, retrieved RAG context (if any), and user prompt into chat messages."""
    system_content = load_system_prompt()

    if retrieved_docs:
        context_parts = []
        for i, doc in enumerate(retrieved_docs, 1):
            category = doc.metadata.get("category", "info")
            filename = doc.metadata.get("filename", "")
            context_parts.append(f"--- Reference Context #{i} [{category} / {filename}] ---\n{doc.page_content}")

        context_block = "\n\n".join(context_parts)
        system_content += f"\n\n## Retrieved Reference Knowledge:\n{context_block}\n"

    messages = [
        ("system", system_content),
        ("human", f"Create a Universal 3D Model Spec JSON for the following description:\n\n{user_description}"),
    ]
    return messages
