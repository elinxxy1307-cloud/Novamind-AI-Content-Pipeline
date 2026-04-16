from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from utils import OUTPUT_DIR, utc_now_iso


@dataclass
class HubSpotConfig:
    access_token: str | None = None
    base_url: str = "https://api.hubapi.com"
    simulate_only: bool = True
    timeout_seconds: int = 20
    persona_property: str | None = None
    log_campaign_notes: bool = True


class HubSpotCRM:
    def __init__(self, config: HubSpotConfig) -> None:
        self.config = config

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.access_token:
            headers["Authorization"] = f"Bearer {self.config.access_token}"
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        response = requests.request(
            method=method,
            url=f"{self.config.base_url}{path}",
            headers=self._headers(),
            timeout=self.config.timeout_seconds,
            **kwargs,
        )
        return response

    def _build_contact_properties(self, contact: dict[str, Any]) -> dict[str, Any]:
        properties = {
            "email": contact["email"],
            "firstname": contact.get("firstname", ""),
            "lastname": contact.get("lastname", ""),
            "company": contact.get("company", ""),
            "jobtitle": contact.get("jobtitle", ""),
            "unsubscribed": contact.get("unsubscribed"),
        }

        if self.config.persona_property:
            properties[self.config.persona_property] = contact.get("persona_segment", "")

        if "version" in contact:
            properties["newsletter_version"] = contact["version"]

        if "email_opened" in contact:
            properties["email_opened"] = contact["email_opened"]

        if "email_clicked" in contact:
            properties["email_clicked"] = contact["email_clicked"]

        if "converted" in contact:
            properties["converted"] = contact["converted"]

        if "unsubscribed" in contact:
            properties["unsubscribed"] = contact["unsubscribed"]

        return properties

    def _create_or_update_contact(self, contact: dict[str, str]) -> dict[str, Any]:
        properties = self._build_contact_properties(contact)
        payload = {"properties": properties}

        create_response = self._request("POST", "/crm/v3/objects/contacts", json=payload)
        if create_response.status_code in {200, 201}:
            data = create_response.json()
            return {
                "mode": "live",
                "action": "created",
                "email": contact["email"],
                "hubspot_contact_id": data.get("id"),
                "status_code": create_response.status_code,
                "response": data,
            }

        if create_response.status_code == 409:
            update_response = self._request(
                "PATCH",
                f"/crm/v3/objects/contacts/{contact['email']}?idProperty=email",
                json={"properties": properties},
            )
            update_response.raise_for_status()
            data = update_response.json()
            return {
                "mode": "live",
                "action": "updated",
                "email": contact["email"],
                "hubspot_contact_id": data.get("id"),
                "status_code": update_response.status_code,
                "response": data,
            }

        create_response.raise_for_status()
        raise RuntimeError("Unexpected HubSpot response while upserting contact.")

    def upsert_contacts(self, contacts: list[dict[str, str]]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        email_to_contact_id: dict[str, str] = {}

        for contact in contacts:
            payload = {"properties": self._build_contact_properties(contact)}
            if self.config.simulate_only:
                results.append(
                    {
                        "mode": "simulated",
                        "action": "would_upsert",
                        "email": contact["email"],
                        "hubspot_contact_id": f"sim_{contact['email']}",
                        "endpoint": "/crm/v3/objects/contacts",
                        "payload": payload,
                    }
                )
                email_to_contact_id[contact["email"]] = f"sim_{contact['email']}"
                continue

            result = self._create_or_update_contact(contact)
            results.append(result)
            if result.get("hubspot_contact_id"):
                email_to_contact_id[contact["email"]] = str(result["hubspot_contact_id"])

        return {
            "created_or_updated": len(results),
            "results": results,
            "email_to_contact_id": email_to_contact_id,
        }

    def _create_note(self, body: str, timestamp_iso: str) -> str | None:
        note_payload = {
            "properties": {
                "hs_timestamp": timestamp_iso,
                "hs_note_body": body,
            }
        }
        response = self._request("POST", "/crm/v3/objects/notes", json=note_payload)
        response.raise_for_status()
        return str(response.json().get("id"))

    def _associate_note_to_contact(self, note_id: str, contact_id: str) -> None:
        response = self._request(
            "PUT",
            f"/crm/v3/objects/notes/{note_id}/associations/contact/{contact_id}/note_to_contact",
        )
        response.raise_for_status()

    def log_campaigns(
        self,
        campaign_rows: list[dict[str, str]],
        send_events: list[dict[str, Any]] | None = None,
        email_to_contact_id: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        log_path = OUTPUT_DIR / "campaign_log.csv"
        file_exists = log_path.exists()
        with log_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "campaign_id",
                    "blog_title",
                    "newsletter_id",
                    "persona_segment",
                    "version",
                    "version_label",
                    "send_date",
                    "recipient_count",
                    "crm_mode",
                ],
            )
            if not file_exists:
                writer.writeheader()
            for row in campaign_rows:
                writer.writerow(row)

        note_results: list[dict[str, Any]] = []
        send_lookup = {row["newsletter_id"]: row for row in (send_events or [])}
        email_to_contact_id = email_to_contact_id or {}

        if self.config.log_campaign_notes:
            for row in campaign_rows:
                event = send_lookup.get(row["newsletter_id"], {})
                recipient_emails = event.get("recipient_emails", [])
                contact_ids = [email_to_contact_id[email] for email in recipient_emails if email in email_to_contact_id]
                note_body = (
                    f"Campaign logged by NovaMind pipeline.<br>"
                    f"Blog title: {row['blog_title']}<br>"
                    f"Newsletter ID: {row['newsletter_id']}<br>"
                    f"Persona segment: {row['persona_segment']}<br>"
                    f"Version: {row['version']} ({row['version_label']})<br>"
                    f"Send date: {row['send_date']}<br>"
                    f"Recipient count: {row['recipient_count']}"
                )

                if self.config.simulate_only:
                    note_results.append(
                        {
                            "mode": "simulated",
                            "newsletter_id": row["newsletter_id"],
                            "associated_contacts": len(contact_ids),
                            "endpoint": "/crm/v3/objects/notes",
                            "body": note_body,
                        }
                    )
                    continue

                note_id = self._create_note(note_body, row["send_date"])
                associated = 0
                for contact_id in contact_ids:
                    self._associate_note_to_contact(note_id=note_id, contact_id=contact_id)
                    associated += 1
                note_results.append(
                    {
                        "mode": "live",
                        "newsletter_id": row["newsletter_id"],
                        "note_id": note_id,
                        "associated_contacts": associated,
                    }
                )

        return {
            "logged_rows": len(campaign_rows),
            "logged_at": utc_now_iso(),
            "log_file": str(log_path),
            "note_results": note_results,
        }


def load_contacts_from_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))
