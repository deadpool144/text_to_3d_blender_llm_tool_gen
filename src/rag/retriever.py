from typing import List, Optional, Dict, Any
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever

from src.rag.embedder_model import get_gemini_embeddings
from vectorstore.store_factory import (
    get_vector_store,
    VectorStoreType,
    DEFAULT_CHROMA_DIR,
)


def get_retriever(
    store_type: VectorStoreType = "chroma",
    persist_dir: Optional[str] = None,
    collection_name: str = "3d_gen_rag",
    top_k: int = 4,
    filter_category: Optional[str] = None,
) -> VectorStoreRetriever:
    """Return a LangChain VectorStoreRetriever with optional metadata filtering.

    Args:
        store_type: 'chroma' or 'faiss'.
        persist_dir: Storage directory.
        collection_name: Chroma collection name.
        top_k: Number of relevant documents to retrieve.
        filter_category: Optional filter by 'docs', 'schemas', or 'premade_models'.

    Returns:
        Configured VectorStoreRetriever.
    """
    embeddings = get_gemini_embeddings()
    vector_store = get_vector_store(
        embeddings=embeddings,
        store_type=store_type,
        persist_dir=persist_dir or DEFAULT_CHROMA_DIR,
        collection_name=collection_name,
    )

    search_kwargs: Dict[str, Any] = {"k": top_k}
    if filter_category:
        search_kwargs["filter"] = {"category": filter_category}

    return vector_store.as_retriever(
        search_type="similarity",
        search_kwargs=search_kwargs,
    )


def query_rag(
    query: str,
    store_type: VectorStoreType = "chroma",
    top_k: int = 4,
    category: Optional[str] = None,
) -> List[Document]:
    """Execute a similarity search on the vector store.

    Args:
        query: User prompt or query text.
        store_type: 'chroma' or 'faiss'.
        top_k: Number of results.
        category: Filter by specific category ('docs', 'schemas', 'premade_models').

    Returns:
        List of matching Document objects.
    """
    retriever = get_retriever(
        store_type=store_type,
        top_k=top_k,
        filter_category=category,
    )
    return retriever.invoke(query)


if __name__ == "__main__":
    try:
        sample_results = query_rag("Blender create cube with materials", top_k=2)
        print(f"Retrieved {len(sample_results)} results:")
        for r in sample_results:
            print(f"- [{r.metadata.get('category')}] {r.metadata.get('filename')}: {r.page_content[:80]}...")
    except Exception as e:
        print(f"Query test (make sure ingest has run): {e}")
