from __future__ import annotations

import requests
from dotenv import load_dotenv

from utils import get_env

load_dotenv()


def main() -> None:
    token = get_env("HUBSPOT_ACCESS_TOKEN")
    if not token:
        raise ValueError("Missing HUBSPOT_ACCESS_TOKEN in .env")

    url = "https://api.hubapi.com/crm/v3/objects/contacts"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = {
        "properties": {
            "email": "test1@example.com",
            "firstname": "Xinyi",
            "lastname": "Xu",
            "company": "NovaMind",
            "jobtitle": "Test Contact",
        }
    }

    response = requests.post(url, headers=headers, json=data, timeout=20)
    print("status_code=", response.status_code)
    try:
        print(response.json())
    except Exception:
        print(response.text)


if __name__ == "__main__":
    main()
