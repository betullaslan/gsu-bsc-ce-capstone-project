"""Parsing and structural validation for generated test-case text."""

import re
from typing import Any, Dict, List


REQUIRED_SECTIONS = [
    "Preconditions",
    "Test Steps",
    "Expected Results",
]


def sanitize_output_text(text: str) -> str:
    """Normalize raw model output text for downstream parsing and validation."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]

    cleaned: List[str] = []
    blank_run = 0
    for line in lines:
        if not line.strip():
            blank_run += 1
            if blank_run <= 1:
                cleaned.append("")
            continue
        blank_run = 0
        cleaned.append(line)

    return "\n".join(cleaned).strip()


def _collapse_ws(text: str) -> str:
    """Collapse repeated whitespace and trim."""
    return re.sub(r"\s+", " ", text).strip()


def _capitalize_leading_alpha(text: str) -> str:
    """Capitalize leading alphabetic character when safe."""
    t = (text or "").strip()
    if not t:
        return t
    if t[0] in {'"', "`"}:
        return t
    if re.match(r"^(id|content|body)\s*:", t, flags=re.IGNORECASE):
        return t
    if "a" <= t[0] <= "z":
        return t[0].upper() + t[1:]
    return t


def _strip_list_prefix(line: str) -> str:
    """Strip common numbering/bullet prefixes from a list item line."""
    # Remove common numbering/bullet prefixes so downstream logic can treat items uniformly.

    if re.match(r"^\s*\d+(\.|\))?\s*$", line):
        return ""

    match = re.match(r"^\s*\d+\.\s*(.*)$", line)
    if match:
        return match.group(1).strip()

    match = re.match(r"^\s*\d+\)\s*(.*)$", line)
    if match:
        return match.group(1).strip()

    match = re.match(r"^\s*[-*]\s+(.*)$", line)
    if match:
        return match.group(1).strip()

    # Handle Unicode bullet characters (or encoding artifacts) that sometimes appear in model output.
    match = re.match(
        r"^\s*(?:[â€¢â€£âˆ™Â·â—â—‹â—¦â–ªâ–«ï¿½]|Ã¢â‚¬Â¢|Ã‚â€¢)\s*(.*)$",
        line,
    )
    if match:
        return match.group(1).strip()

    return line.strip()


def validate_required_sections(text: str, strict_headers: bool = True) -> List[str]:
    """Return a list of required section names missing from the output text."""
    missing: List[str] = []
    for section in REQUIRED_SECTIONS:
        if strict_headers:
            pattern = rf"^{re.escape(section)}\s*:\s*$"
            ok = bool(re.search(pattern, text, flags=re.MULTILINE))
        else:
            pattern = rf"^\s*{re.escape(section)}\s*:"
            ok = bool(re.search(pattern, text, flags=re.MULTILINE | re.IGNORECASE))
        if not ok:
            missing.append(section)
    return missing


def _is_placeholder_item(item: str) -> bool:
    """Return True for placeholders or non-content list artifacts."""
    if not item:
        return True
    if item == "-":
        return True

    if re.fullmatch(r"\d+(\.|\))?", item.strip()):
        return True
    if re.fullmatch(r"\.{3,}", item):
        return True
    if re.match(
        r"^(N/A|TBD|TODO|XXX|FIXME|example|\?|\[PLACEHOLDER\]|<TBD>)$",
        item,
        re.IGNORECASE,
    ):
        return True
    if re.match(r"^(not\s+specified|to\s+be\s+defined)$", item, re.IGNORECASE):
        return True
    return False


def parse_test_case(text: str) -> Dict[str, Any]:
    """Parse the model output text into preconditions, steps, and expected results."""
    normalized = sanitize_output_text(text)

    preconditions: List[str] = []
    steps: List[str] = []
    expected_results: List[str] = []

    current_section: str = ""

    def set_section(section_name: str, remainder: str) -> None:
        """Set current section and consume inline section content if present."""
        nonlocal current_section, preconditions, steps, expected_results
        current_section = section_name
        remainder = remainder.strip()
        if not remainder:
            return

        if section_name == "Preconditions":
            item = _strip_list_prefix(remainder)
            if not _is_placeholder_item(item):
                preconditions.append(_capitalize_leading_alpha(_collapse_ws(item)))
        elif section_name == "Test Steps":
            item = _strip_list_prefix(remainder)
            if not _is_placeholder_item(item):
                steps.append(_capitalize_leading_alpha(_collapse_ws(item)))
        elif section_name == "Expected Results":
            item = _strip_list_prefix(remainder)
            if not _is_placeholder_item(item):
                expected_results.append(_capitalize_leading_alpha(_collapse_ws(item)))

    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        heading_match = re.match(
            r"^(Preconditions|Test Steps|Expected Results)\s*:\s*(.*)$",
            line,
            flags=re.IGNORECASE,
        )
        if heading_match:
            heading = heading_match.group(1)
            remainder = heading_match.group(2)
            canonical_heading = next(
                sec for sec in REQUIRED_SECTIONS if sec.lower() == heading.lower()
            )
            set_section(canonical_heading, remainder)
            continue

        if current_section == "Preconditions":
            item = _strip_list_prefix(line)
            if not _is_placeholder_item(item):
                preconditions.append(_capitalize_leading_alpha(_collapse_ws(item)))
            continue

        if current_section == "Test Steps":
            item = _strip_list_prefix(line)
            if not _is_placeholder_item(item):
                steps.append(_capitalize_leading_alpha(_collapse_ws(item)))
            continue

        if current_section == "Expected Results":
            item = _strip_list_prefix(line)
            if not _is_placeholder_item(item):
                expected_results.append(_capitalize_leading_alpha(_collapse_ws(item)))
            continue

    return {
        "preconditions": preconditions,
        "steps": steps,
        "expected_results": expected_results,
    }


def validate_structure(output_text: str, parsed: Dict[str, Any]) -> List[str]:
    """Validate required sections and non-empty lists; returns critical error codes."""
    missing_sections = validate_required_sections(output_text, strict_headers=True)
    critical: List[str] = []

    if missing_sections:
        critical.append("missing_required_sections")

    if not parsed.get("steps"):
        critical.append("missing_test_steps")

    if not parsed.get("expected_results"):
        critical.append("missing_expected_results")

    if (
        not parsed.get("preconditions")
        and not parsed.get("steps")
        and not parsed.get("expected_results")
    ):
        critical.append("empty_test_case")

    return critical
