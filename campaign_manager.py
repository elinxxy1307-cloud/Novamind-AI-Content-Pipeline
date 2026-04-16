from __future__ import annotations

from collections import defaultdict
from typing import Any

from utils import safe_slug, utc_now_iso


VALID_VERSIONS = ["A", "B"]


def build_newsletter_lookup(newsletters: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    return {(item["persona"], item["version"]): item for item in newsletters}


def assign_newsletters_to_segments(
    contacts: list[dict[str, str]],
    newsletters: list[dict[str, str]],
    blog_title: str,
    simulate_only: bool = True,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for contact in contacts:
        grouped[contact["persona_segment"]].append(contact)

    newsletter_lookup = build_newsletter_lookup(newsletters)
    send_date = utc_now_iso()
    campaign_id = f"cmp_{safe_slug(blog_title)}_{send_date[:10].replace('-', '')}"

    send_events: list[dict[str, Any]] = []
    campaign_rows: list[dict[str, str]] = []

    for persona, recipients in grouped.items():
        recipient_versions: dict[str, list[dict[str, str]]] = {"A": [], "B": []}

        for idx, recipient in enumerate(recipients):
            assigned_version = VALID_VERSIONS[idx % len(VALID_VERSIONS)]
            recipient["version"] = assigned_version
            recipient["campaign_id"] = campaign_id
            recipient["newsletter_id"] = f"nl_{safe_slug(persona)}_{assigned_version}_{send_date[:10].replace('-', '')}"

            newsletter = newsletter_lookup.get((persona, assigned_version))
            recipient["version_label"] = newsletter.get("version_label", "") if newsletter else ""

            recipient_versions[assigned_version].append(recipient)

        for version, version_recipients in recipient_versions.items():
            if not version_recipients:
                continue

            newsletter = newsletter_lookup.get((persona, version))
            if not newsletter:
                continue

            newsletter_id = f"nl_{safe_slug(persona)}_{version}_{send_date[:10].replace('-', '')}"
            send_events.append(
                {
                    "campaign_id": campaign_id,
                    "newsletter_id": newsletter_id,
                    "persona_segment": persona,
                    "version": version,
                    "version_label": newsletter.get("version_label", ""),
                    "subject": newsletter["subject"],
                    "preview_text": newsletter["preview_text"],
                    "recipient_emails": [r["email"] for r in version_recipients],
                    "recipient_count": len(version_recipients),
                    "send_mode": "simulated" if simulate_only else "live",
                    "send_date": send_date,
                }
            )
            campaign_rows.append(
                {
                    "campaign_id": campaign_id,
                    "blog_title": blog_title,
                    "newsletter_id": newsletter_id,
                    "persona_segment": persona,
                    "version": version,
                    "version_label": newsletter.get("version_label", ""),
                    "send_date": send_date,
                    "recipient_count": str(len(version_recipients)),
                    "crm_mode": "simulated" if simulate_only else "live",
                }
            )

    return {"campaign_id": campaign_id, "send_events": send_events, "campaign_rows": campaign_rows}
