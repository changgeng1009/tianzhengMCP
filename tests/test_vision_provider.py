import pytest


def test_openai_provider_builds_configurable_gpt55_original_detail_payload() -> None:
    from vision.provider import ImageInput, OpenAIVisionProvider, VisionProviderConfig

    provider = OpenAIVisionProvider(
        VisionProviderConfig(model="gpt-5.5", image_detail="original")
    )
    image = ImageInput.from_url("https://example.com/reference.png")

    payload = provider.build_responses_payload(image)

    assert payload["model"] == "gpt-5.5"
    input_image = payload["input"][1]["content"][1]
    assert input_image == {
        "type": "input_image",
        "image_url": "https://example.com/reference.png",
        "detail": "original",
    }
    assert payload["text"]["format"]["type"] == "json_schema"


def test_vision_provider_allows_high_detail_for_cost_sensitive_runs() -> None:
    from vision.provider import ImageInput, OpenAIVisionProvider, VisionProviderConfig

    provider = OpenAIVisionProvider(
        VisionProviderConfig(model="gpt-5.5", image_detail="high")
    )

    payload = provider.build_responses_payload(
        ImageInput.from_url("https://example.com/reference.jpg")
    )

    assert payload["input"][1]["content"][1]["detail"] == "high"


def test_vision_provider_rejects_unsupported_image_detail() -> None:
    from vision.provider import VisionProviderConfig

    with pytest.raises(ValueError, match="image_detail"):
        VisionProviderConfig(model="gpt-5.5", image_detail="medium")
