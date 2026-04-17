"""Privacy enforcement for project data.

Strips private sections from project markdown before exposing to external consumers.
"""

import re

_PRIVATE_HEADINGS = {"notes", "personal"}


def strip_private_sections(markdown: str) -> str:
    """Remove ## Notes, ## Personal, and other private sections from markdown.

    Strips everything from a private heading to the next ## heading or end-of-file.
    """
    # Split on ## headings, keeping the delimiter
    parts = re.split(r"(^## .+$)", markdown, flags=re.MULTILINE)

    result = []
    skip = False
    for part in parts:
        # Check if this part is a heading
        heading_match = re.match(r"^## (.+)$", part.strip())
        if heading_match:
            heading_name = heading_match.group(1).strip().lower()
            if heading_name in _PRIVATE_HEADINGS:
                skip = True
                continue
            else:
                skip = False

        if not skip:
            result.append(part)

    return "".join(result)
