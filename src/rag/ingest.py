import os
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from typing import List, Optional
from langchain_core.documents import Document

from src.rag.chunking import chunk_documents_file, chunk_json_file
from src.rag.embedder_model import get_gemini_embeddings
from vectorstore.store_factory import (
    create_vector_store_from_documents,
    VectorStoreType,
    DEFAULT_CHROMA_DIR,
)

BASE_DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data")
)


def load_all_documents(data_dir: str = BASE_DATA_DIR) -> List[Document]:
    """Scan the data directory and subfolders (docs, schemas, premade_models)
    and parse documents according to their specific strategy.

    - docs: Semantic text chunking for markdown/text files.
    - schemas & premade_models: Structured JSON parsing emphasizing file name and description.
    """
    all_docs: List[Document] = []

    # 1. Ingest docs/ (semantic chunking)
    docs_dir = os.path.join(data_dir, "docs")
    if os.path.exists(docs_dir):
        for root, _, files in os.walk(docs_dir):
            for file in files:
                file_path = os.path.join(root, file)
                if file.lower().endswith((".txt", ".md", ".rst", ".py")):
                    chunks = chunk_documents_file(file_path)
                    all_docs.extend(chunks)

    # 2. Ingest schemas/ (JSON description & file name based)
    schemas_dir = os.path.join(data_dir, "schemas")
    if os.path.exists(schemas_dir):
        for root, _, files in os.walk(schemas_dir):
            for file in files:
                file_path = os.path.join(root, file)
                if file.lower().endswith(".json"):
                    all_docs.extend(chunk_json_file(file_path, category="schemas"))
                elif file.lower().endswith((".txt", ".md", ".yaml", ".yml")):
                    all_docs.extend(chunk_documents_file(file_path))

    # 3. Ingest premade_models/ (JSON description & file name based)
    premade_dir = os.path.join(data_dir, "premade_models")
    if os.path.exists(premade_dir):
        for root, _, files in os.walk(premade_dir):
            for file in files:
                file_path = os.path.join(root, file)
                if file.lower().endswith(".json"):
                    all_docs.extend(chunk_json_file(file_path, category="premade_models"))
                elif file.lower().endswith((".txt", ".md", ".py")):
                    all_docs.extend(chunk_documents_file(file_path))

    return all_docs


def ingest_data(
    data_dir: str = BASE_DATA_DIR,
    store_type: VectorStoreType = "chroma",
    persist_dir: Optional[str] = None,
    collection_name: str = "3d_gen_rag",
):
    """Ingest data from all subdirectories into the vector store."""
    print(f"Loading documents from: {data_dir}")
    documents = load_all_documents(data_dir)
    print(f"Total documents/chunks prepared: {len(documents)}")

    if not documents:
        print("Warning: No documents found in data folder to ingest.")
        return None

    print(f"Initializing embedding model...")
    embeddings = get_gemini_embeddings()

    print(f"Storing embeddings in {store_type.upper()}...")
    vector_store = create_vector_store_from_documents(
        documents=documents,
        embeddings=embeddings,
        store_type=store_type,
        persist_dir=persist_dir or DEFAULT_CHROMA_DIR,
        collection_name=collection_name,
    )
    print(f"Successfully ingested and persisted {len(documents)} items into {store_type.upper()}.")
    return vector_store


if __name__ == "__main__":
    ingest_data(store_type="chroma")
