import os
from typing import Literal, Optional, List
from langchain_core.vectorstores import VectorStore
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document

VectorStoreType = Literal["chroma", "faiss"]

DEFAULT_CHROMA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "vectorstore", "chroma_db")
)
DEFAULT_FAISS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "vectorstore", "faiss_index")
)


def get_vector_store(
    embeddings: Embeddings,
    store_type: VectorStoreType = "chroma",
    persist_dir: Optional[str] = None,
    collection_name: str = "rag_collection",
) -> VectorStore:
    """Load or initialize an existing vector store (Chroma or FAISS).

    Args:
        embeddings: The embedding function / model instance.
        store_type: 'chroma' or 'faiss'.
        persist_dir: Directory where the index/database is saved.
        collection_name: Collection name (used by Chroma).

    Returns:
        VectorStore instance.
    """
    if store_type == "chroma":
        from langchain_chroma import Chroma

        target_dir = persist_dir or DEFAULT_CHROMA_DIR
        os.makedirs(target_dir, exist_ok=True)
        return Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=target_dir,
        )

    elif store_type == "faiss":
        from langchain_community.vectorstores import FAISS

        target_dir = persist_dir or DEFAULT_FAISS_DIR
        if os.path.exists(target_dir) and os.path.exists(os.path.join(target_dir, "index.faiss")):
            return FAISS.load_local(
                folder_path=target_dir,
                embeddings=embeddings,
                allow_dangerous_deserialization=True,
            )
        else:
            # If not yet saved on disk, create an empty FAISS vectorstore with dummy document and clean it
            # Or initialize lazily when creating from documents
            raise FileNotFoundError(
                f"FAISS index not found at '{target_dir}'. Use create_vector_store_from_documents first."
            )
    else:
        raise ValueError(f"Unsupported store_type: {store_type}. Choose 'chroma' or 'faiss'.")


def create_vector_store_from_documents(
    documents: List[Document],
    embeddings: Embeddings,
    store_type: VectorStoreType = "chroma",
    persist_dir: Optional[str] = None,
    collection_name: str = "rag_collection",
) -> VectorStore:
    """Create and persist a vector store from a list of Document objects.

    Args:
        documents: List of Document objects to ingest.
        embeddings: Embeddings instance.
        store_type: 'chroma' or 'faiss'.
        persist_dir: Directory to persist data.
        collection_name: Collection name for Chroma.

    Returns:
        Persisted VectorStore instance.
    """
    if not documents:
        raise ValueError("Cannot create vector store from empty documents list.")

    if store_type == "chroma":
        from langchain_chroma import Chroma

        target_dir = persist_dir or DEFAULT_CHROMA_DIR
        os.makedirs(target_dir, exist_ok=True)
        vector_store = Chroma.from_documents(
            documents=documents,
            embedding=embeddings,
            persist_directory=target_dir,
            collection_name=collection_name,
        )
        return vector_store

    elif store_type == "faiss":
        from langchain_community.vectorstores import FAISS

        target_dir = persist_dir or DEFAULT_FAISS_DIR
        os.makedirs(target_dir, exist_ok=True)
        vector_store = FAISS.from_documents(
            documents=documents,
            embedding=embeddings,
        )
        vector_store.save_local(folder_path=target_dir)
        return vector_store

    else:
        raise ValueError(f"Unsupported store_type: {store_type}. Choose 'chroma' or 'faiss'.")
