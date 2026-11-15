import os
from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings


def load_environment() -> None:
    """Load environment variables from .env file."""
    load_dotenv()


def get_gemini_embeddings(
    model_name: str = "models/gemini-embedding-2",
    **kwargs,
) -> GoogleGenerativeAIEmbeddings:
    
    load_environment()

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise ValueError(
            "GOOGLE_API_KEY is not set or still contains the placeholder value in .env. "
            "Please provide a valid Google Gemini API key."
        )

    return GoogleGenerativeAIEmbeddings(
        model=model_name,
        google_api_key=api_key,
        **kwargs,
    )


if __name__ == "__main__":
    try:
        embeddings = get_gemini_embeddings()
        vector = embeddings.embed_query("Test embedding generation")
        print(f"Successfully generated embedding vector of length: {len(vector)}")
    except Exception as e:
        print(f"Initialization check: {e}")
