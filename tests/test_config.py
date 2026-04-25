from ui_bot.config import Settings


def test_cors_origins_are_split() -> None:
    settings = Settings(UI_BOT_ALLOWED_ORIGINS="http://a.test, http://b.test")

    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_provider_is_normalized() -> None:
    settings = Settings(LLM_PROVIDER=" OpenRouter ")

    assert settings.llm_provider == "openrouter"


def test_openrouter_model_list_prefers_primary() -> None:
    settings = Settings(
        OPENROUTER_MODEL="primary:free",
        OPENROUTER_MODELS="fallback-one:free,fallback-two:free",
    )

    assert settings.openrouter_model_list == [
        "primary:free",
        "fallback-one:free",
        "fallback-two:free",
    ]
