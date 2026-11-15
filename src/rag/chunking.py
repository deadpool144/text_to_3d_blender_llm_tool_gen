import json
import os
from typing import List, Dict, Any
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


def get_text_splitter(
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> RecursiveCharacterTextSplitter:
    """Return a RecursiveCharacterTextSplitter configured for document chunking."""
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
    )


def chunk_documents_file(
    file_path: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> List[Document]:
    """Read a text or markdown file and return chunked Document objects.

    Args:
        file_path: Path to the text/markdown document.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Overlap between consecutive chunks.

    Returns:
        List of langchain Document chunks.
    """
    if not os.path.exists(file_path):
        return []

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    splitter = get_text_splitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    filename = os.path.basename(file_path)

    raw_docs = [
        Document(
            page_content=text,
            metadata={
                "source": file_path,
                "filename": filename,
                "category": "docs",
            },
        )
    ]
    return splitter.split_documents(raw_docs)


def chunk_json_file(file_path: str, category: str) -> List[Document]:
    """Parse JSON files (for schemas or premade models) and create structured Document objects.

    Uses description, name/filename, and schema details for targeted retrieval.

    Args:
        file_path: Absolute or relative path to the JSON file.
        category: 'schemas' or 'premade_models'.

    Returns:
        List of Document objects representing schema or pre-made items.
    """
    if not os.path.exists(file_path):
        return []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Failed to parse JSON file {file_path}: {e}")
        return []

    filename = os.path.basename(file_path)
    file_stem = os.path.splitext(filename)[0]

    # Support single dict or list of dicts in JSON
    items = data if isinstance(data, list) else [data]
    docs: List[Document] = []

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            content = str(item)
            name = f"{file_stem}_{idx}"
            desc = ""
        else:
            name = item.get("name") or item.get("title") or item.get("id") or file_stem
            desc = item.get("description") or item.get("summary") or item.get("desc") or ""

            # Structured text prioritizing name, description, and key attributes
            content_lines = [
                f"File: {filename}",
                f"Item Name: {name}",
                f"Category: {category}",
            ]
            if desc:
                content_lines.append(f"Description: {desc}")

            # Include remaining attributes for comprehensive context
            details = {k: v for k, v in item.items() if k not in ["name", "title", "id", "description", "summary", "desc"]}
            if details:
                content_lines.append(f"Details: {json.dumps(details, indent=2)}")

            content = "\n".join(content_lines)

        metadata: Dict[str, Any] = {
            "source": file_path,
            "filename": filename,
            "category": category,
            "name": str(name),
            "description": str(desc),
        }

        docs.append(Document(page_content=content, metadata=metadata))

    return docs
