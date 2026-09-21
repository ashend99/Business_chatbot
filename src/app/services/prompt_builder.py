"""Assembles the bot's system prompt per request from the sections in
project_config.yaml (`agent.prompt`) and the tenant's effective settings, so
the prompt only ever describes tools the agent actually has and reflects
that tenant's rules (fulfillment options, minimum order, negotiation policy,
human vs bot order confirmation, currency, timezone, persona).

Pure function of its inputs -- no I/O -- so it's cheap to call every turn
and easy to unit test.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.money import format_money
from app.services.settings_resolver import EffectiveSettings
from common import PROJECT_CONFIG


def enabled_tool_names(settings: EffectiveSettings) -> list[str]:
    """The tools this tenant's agent gets -- shared with bot_tools.build_tools
    so the prompt and the toolset can never disagree."""
    names = []
    if settings.documents_enabled:
        names.append("search_documents")
    if settings.catalog_enabled:
        names.extend(["search_catalog", "browse_catalog"])
    if settings.leads_enabled:
        names.append("create_lead")
    if settings.ordering_enabled and settings.catalog_enabled:
        # an order is built out of catalog variants -- no catalog, no cart
        names.extend(["update_order", "confirm_order"])
    return names


def ordering_active(settings: EffectiveSettings) -> bool:
    return "update_order" in enabled_tool_names(settings)


def local_now(settings: EffectiveSettings) -> datetime:
    return datetime.now(ZoneInfo(settings.timezone))


def build_system_prompt(settings: EffectiveSettings, tenant_name: str, now: datetime | None = None) -> str:
    cfg = PROJECT_CONFIG.get("agent").get("prompt")
    tools = cfg.get("tools")
    now = now or local_now(settings)
    tool_names = enabled_tool_names(settings)
    ordering = ordering_active(settings)

    parts: list[str] = [
        cfg.get("identity")
        .format(
            bot_name_clause=f"{settings.bot_name}, " if settings.bot_name else "",
            tone=cfg.get("tones").get(settings.tone.value),
            tenant_name=tenant_name,
            language=settings.language,
            now=now.strftime("%A, %d %B %Y, %I:%M %p (%Z)"),
        )
        .strip()
    ]

    if tool_names:
        section_keys = [
            ("confirm_order_human" if settings.human_confirmation else "confirm_order_bot") if n == "confirm_order" else n
            for n in tool_names
        ]
        parts.append(cfg.get("tools_intro") + "\n\n" + "\n".join(tools.get(k).rstrip() for k in section_keys))

    order_cfg = cfg.get("ordering")
    if ordering:
        lines = [(order_cfg.get("intro_human") if settings.human_confirmation else order_cfg.get("intro_bot")).strip()]
        if settings.fulfillment_types:
            lines.append(order_cfg.get("fulfillment").format(types=" and ".join(settings.fulfillment_types)))
        if settings.min_order_value:
            lines.append(
                order_cfg.get("min_order").format(amount=format_money(settings.min_order_value, settings.currency_code))
            )
        if settings.cash_on_delivery and settings.delivery_enabled:
            lines.append(order_cfg.get("cash_on_delivery"))
        parts.append("\n".join(lines))
    else:
        parts.append(order_cfg.get("disabled").strip())

    parts.append(cfg.get("negotiation").get(settings.negotiation_mode.value).strip())

    rules_cfg = cfg.get("rules")
    price_tools = [n for n in ("search_catalog", "browse_catalog", "update_order", "confirm_order") if n in tool_names]
    rules: list[str] = []
    if price_tools:
        rules.append(
            rules_cfg.get("pricing").format(price_tools="/".join(price_tools), currency=settings.currency_code).rstrip()
        )
    if "browse_catalog" in tool_names:
        rules.append(rules_cfg.get("browse_first").rstrip())
    rules.append(rules_cfg.get("honesty").rstrip())
    rules.append(rules_cfg.get("no_cancel").rstrip())
    rules.append(rules_cfg.get("style").rstrip())
    parts.append("Rules:\n" + "\n".join(rules))

    if settings.welcome_message:
        parts.append(cfg.get("welcome").format(message=settings.welcome_message))

    if settings.custom_instructions and settings.custom_instructions.strip():
        parts.append(
            cfg.get("custom_instructions_header").strip()
            + "\n"
            + settings.custom_instructions.strip()
            + "\n\n"
            + cfg.get("custom_instructions_footer").strip()
        )

    return "\n\n".join(parts)
