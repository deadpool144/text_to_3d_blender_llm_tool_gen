import re
import json
from typing import Dict, Any, Tuple, Union


def clean_json_text(raw_text: Union[str, list, dict]) -> str:
    """Extract and sanitize JSON content from raw LLM output."""
    if isinstance(raw_text, list):
        # In case LangChain returns a list of content blocks
        parts = []
        for part in raw_text:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and "text" in part:
                parts.append(part["text"])
        text = "\n".join(parts).strip()
    elif isinstance(raw_text, dict):
        return json.dumps(raw_text)
    else:
        text = str(raw_text).strip()

    # Look for ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()

    return text


def parse_model_spec(raw_text: Union[str, list, dict]) -> Tuple[bool, Dict[str, Any], str]:
    """Parse JSON string or block into a dictionary.

    Returns:
        (is_valid, parsed_dict, error_message)
    """
    clean_text = clean_json_text(raw_text)
    try:
        data = json.loads(clean_text)
        if not isinstance(data, dict):
            return False, {}, "Parsed JSON is not an object/dictionary."
        if "schema_version" not in data or "objects" not in data:
            return False, data, "JSON missing required 'schema_version' or 'objects' keys."
        return True, data, ""
    except json.JSONDecodeError as e:
        return False, {}, f"JSON decode error: {e}"
