from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from utils import OUTPUT_DIR, utc_now_iso


DEFAULT_AB_METRICS: dict[str, dict[str, dict[str, float]]] = {
    "Agency Founder / Owner": {
        "A": {
            "open_rate": 0.48,
            "click_rate": 0.13,
            "unsubscribe_rate": 0.015,
            "conversion_rate": 0.041,
        },
        "B": {
            "open_rate": 0.44,
            "click_rate": 0.17,
            "unsubscribe_rate": 0.013,
            "conversion_rate": 0.053,
        },
    },
    "Operations Manager": {
        "A": {
            "open_rate": 0.42,
            "click_rate": 0.15,
            "unsubscribe_rate": 0.010,
            "conversion_rate": 0.039,
        },
        "B": {
            "open_rate": 0.45,
            "click_rate": 0.13,
            "unsubscribe_rate": 0.009,
            "conversion_rate": 0.035,
        },
    },
    "Marketing / Growth Lead": {
        "A": {
            "open_rate": 0.47,
            "click_rate": 0.16,
            "unsubscribe_rate": 0.019,
            "conversion_rate": 0.050,
        },
        "B": {
            "open_rate": 0.49,
            "click_rate": 0.14,
            "unsubscribe_rate": 0.021,
            "conversion_rate": 0.046,
        },
    },
}


def simulate_performance(send_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    captured_at = utc_now_iso()
    for event in send_events:
        recipient_count = event["recipient_count"]
        version = event["version"]
        base = DEFAULT_AB_METRICS[event["persona_segment"]][version]
        rows.append(
            {
                "captured_at": captured_at,
                "campaign_id": event["campaign_id"],
                "newsletter_id": event["newsletter_id"],
                "persona_segment": event["persona_segment"],
                "version": version,
                "version_label": event.get("version_label", ""),
                "sent_count": recipient_count,
                "open_rate": base["open_rate"],
                "click_rate": base["click_rate"],
                "unsubscribe_rate": base["unsubscribe_rate"],
                "conversion_rate": base["conversion_rate"],
                "opens": round(recipient_count * base["open_rate"]),
                "clicks": round(recipient_count * base["click_rate"]),
                "unsubscribes": round(recipient_count * base["unsubscribe_rate"]),
                "conversions": round(recipient_count * base["conversion_rate"]),
            }
        )
    return rows


def aggregate_from_contacts(contacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    import pandas as pd

    if not contacts:
        return []

    df = pd.DataFrame(contacts)

    grouped = (
        df.groupby(
            ["campaign_id", "newsletter_id", "persona_segment", "version", "version_label"],
            dropna=False,
        )
        .agg(
            sent_count=("email", "count"),
            opens=("email_opened", "sum"),
            clicks=("email_clicked", "sum"),
            conversions=("converted", "sum"),
            unsubscribes=("unsubscribed", "sum"),
        )
        .reset_index()
    )

    grouped["open_rate"] = grouped["opens"] / grouped["sent_count"]
    grouped["click_rate"] = grouped["clicks"] / grouped["sent_count"]
    grouped["conversion_rate"] = grouped["conversions"] / grouped["sent_count"]

    grouped["unsubscribe_rate"] = grouped["unsubscribes"] / grouped["sent_count"]

    grouped["captured_at"] = utc_now_iso()
    
    cols = [
        "captured_at",
        "campaign_id",
        "newsletter_id",
        "persona_segment",
        "version",
        "version_label",
        "sent_count",
        "open_rate",
        "click_rate",
        "unsubscribe_rate",
        "conversion_rate",
        "opens",
        "clicks",
        "unsubscribes",
        "conversions",
    ]
    return grouped[cols].to_dict(orient="records")


def append_performance_history(rows: list[dict[str, Any]], path: Path | None = None) -> Path:
    path = path or OUTPUT_DIR / "performance_history.csv"
    file_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)
    return path


def simulate_contact_outcomes(contacts: list[dict[str, str]]) -> list[dict[str, Any]]:
    import random
    random.seed(617)

    enriched_contacts: list[dict[str, Any]] = []

    for contact in contacts:
        persona = contact["persona_segment"]
        version = contact["version"]
        base = DEFAULT_AB_METRICS[persona][version]

        opened = random.random() < base["open_rate"]
        clicked = opened and (
            random.random() < (base["click_rate"] / base["open_rate"] if base["open_rate"] > 0 else 0)
        )
        converted = clicked and (
            random.random() < (base["conversion_rate"] / base["click_rate"] if base["click_rate"] > 0 else 0)
        )
        unsubscribed = random.random() < base["unsubscribe_rate"]

        enriched = dict(contact)
        enriched["email_opened"] = opened
        enriched["email_clicked"] = clicked
        enriched["converted"] = converted
        enriched["unsubscribed"] = unsubscribed
        enriched_contacts.append(enriched)

    return enriched_contacts
