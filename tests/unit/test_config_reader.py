import pytest

from utils.config import ConfigReader, load_config


def test_attribute_and_dict_access_at_any_depth() -> None:
    config = ConfigReader({"email": {"mail": {"subject": "Hi"}}, "items": [{"name": "a"}]})
    assert config.email.mail.subject == "Hi"
    assert config.get("email").get("mail").get("subject") == "Hi"
    assert config["email"]["mail"]["subject"] == "Hi"
    assert config.items[0].name == "a"
    assert config.get("missing", 42) == 42
    assert "email" in config
    with pytest.raises(AttributeError):
        _ = config.missing


def test_load_config_requires_a_mapping(tmp_path) -> None:
    good = tmp_path / "good.yaml"
    good.write_text("agent:\n  model: test\n", encoding="utf-8")
    assert load_config(good).agent.model == "test"

    bad = tmp_path / "bad.yaml"
    bad.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(bad)


def test_project_config_has_every_prompt_section_the_builder_needs() -> None:
    """prompt_builder reads these keys without defaults -- a missing one
    would crash every bot turn, so catch it here."""
    from common import PROJECT_CONFIG

    prompt = PROJECT_CONFIG.agent.prompt
    for key in (
        "identity",
        "tools_intro",
        "welcome",
        "custom_instructions_header",
        "custom_instructions_footer",
        "default_fallback",
    ):
        assert prompt.get(key), key
    for tool in (
        "search_documents",
        "search_catalog",
        "browse_catalog",
        "update_order",
        "confirm_order_bot",
        "confirm_order_human",
        "create_lead",
    ):
        assert prompt.tools.get(tool), tool
    for key in (
        "intro_bot",
        "intro_human",
        "fulfillment",
        "min_order",
        "cash_on_delivery",
        "disabled",
    ):
        assert prompt.ordering.get(key), key
    for tone in ("formal", "friendly", "casual"):
        assert prompt.tones.get(tone), tone
    for mode in ("fixed", "escalate"):
        assert prompt.negotiation.get(mode), mode
    for mail in (
        "onboard_mail",
        "reset_password_mail",
        "new_lead_mail",
        "new_order_mail",
        "new_order_pending_mail",
    ):
        assert PROJECT_CONFIG.email.get(mail).subject, mail
