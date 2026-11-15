import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI


def load_environment() -> None:
    """Load environment variables from .env file."""
    load_dotenv()


def get_gemini_model(
    model_name: str = "gemini-3.8-flash",
    temperature: float = 0.7,
    **kwargs,
) -> ChatGoogleGenerativeAI:
    load_environment()

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise ValueError(
            "GOOGLE_API_KEY is not set or still contains the placeholder value in .env. "
            "Please provide a valid Google Gemini API key."
        )

    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=temperature,
        **kwargs,
    )


if __name__ == "__main__":
    try:
        llm = get_gemini_model()
        print(f"Successfully initialized model: {llm.model}")
    except Exception as e:
        print(f"Initialization check: {e}")

