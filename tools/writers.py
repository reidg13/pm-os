"""Write tools for Cars Copilot.

Only one write operation: appending feature requests to a Google Sheet.
No vault modifications. No roadmap edits.
"""

import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pm.config import GOOGLE_CREDS_FILE, GOOGLE_TOKEN_FILE

_ROADMAP_SHEET_ID = "YOUR_SPREADSHEET_ID"
_FEATURE_REQUEST_TAB = "Feature Request"
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_sheets_service():
    """Return authenticated Google Sheets API service, or None if not configured."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        return None

    if not os.path.exists(GOOGLE_TOKEN_FILE):
        return None

    creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_FILE, _SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Save refreshed token
        with open(GOOGLE_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("sheets", "v4", credentials=creds)


def submit_feature_request(
    description: str,
    submitted_by: str,
    source: str = "",
) -> str:
    """Append a feature request to the YOUR_ROADMAP_TAB Google Sheet.

    Returns a confirmation message or a friendly error if not configured.
    """
    service = _get_sheets_service()
    if service is None:
        return (
            "Feature request noted but Google Sheets is not yet configured. "
            "The request was: " + description
        )

    row = [
        date.today().isoformat(),
        description,
        submitted_by,
        source,
        "New",
    ]

    try:
        service.spreadsheets().values().append(
            spreadsheetId=_ROADMAP_SHEET_ID,
            range=f"'{_FEATURE_REQUEST_TAB}'!A:E",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
        return f"Feature request submitted: '{description}' (by {submitted_by})"
    except Exception as e:
        return f"Error submitting feature request: {e}"
