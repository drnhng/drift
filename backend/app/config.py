from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Any OpenAI-compatible chat API works. Defaults target Gemini's free tier.

    Groq (also free):  LLM_BASE_URL=https://api.groq.com/openai/v1
                       LLM_MODEL=llama-3.3-70b-versatile
    Leave LLM_API_KEY empty to use only the built-in rule parser.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_api_key: str = ""
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_model: str = "gemini-2.5-flash"
    llm_timeout_seconds: float = 12.0

    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
