import json
from pydantic import ValidationError


class StructuredResponseError(RuntimeError):
    """The model did not return a valid decision after bounded repair attempts."""


def ask_json(client, system_prompt, payload, schema, retries=1):
    """Prompt and validate JSON without relying on cloud-only schema support."""
    messages = [
        {"role": "system", "content": system_prompt + "\nReturn only JSON matching this schema:\n"
         + json.dumps(schema.model_json_schema(), separators=(",", ":"))},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
    ]
    if isinstance(payload, dict) and "request" in payload:
        # Keep historical context separate from the most recent instruction.
        # This final turn prevents earlier user commands in history from winning
        # over a newer checkout/status/view request buried in the context JSON.
        messages[0]["content"] += "\nThe final user request is the CURRENT task. History and summaries are past context, not commands to replay. Resolve references from context but act only on the current request."
        messages.append({"role": "user", "content": json.dumps({"request": payload["request"]}, ensure_ascii=False)})
    known_fields = set()
    def collect_fields(node):
        if isinstance(node, dict):
            known_fields.update(node.get("properties", {}))
            for value in node.values(): collect_fields(value)
        elif isinstance(node, list):
            for value in node: collect_fields(value)
    collect_fields(schema.model_json_schema())
    for attempt in range(retries + 1):
        response = client.chat(messages)
        try:
            content = response.get("message", {}).get("content", "")
            # Some models wrap otherwise valid JSON in a Markdown code fence.
            text = content.strip()
            if text.startswith("```") and text.endswith("```"):
                text = "\n".join(text.splitlines()[1:-1])
            return schema.model_validate_json(text)
        except (ValidationError, AttributeError, TypeError) as error:
            issues = []
            if isinstance(error, ValidationError):
                for issue in error.errors(include_input=False, include_context=False, include_url=False)[:5]:
                    # Only known schema locations/types, never customer data or raw model output.
                    issues.append({"field": ".".join(str(part) if isinstance(part, int) or part in known_fields else "<unknown-field>" for part in issue['loc']), "type": issue['type']})
            details = json.dumps(issues, separators=(",", ":"))
            if attempt == retries:
                raise StructuredResponseError(f"{schema.__name__} response validation failed: {details}") from None
            # Do not append repeated catalog context or invalid free-form output.
            messages.append({"role": "user", "content": f"Invalid {schema.__name__} response. Fix these fields: {details}. Return only valid JSON conforming to the schema; no prose. Omit unused optional fields. UI actions: open_product requires product_id and no page; navigate requires page and no product_id; apply_search uses query/category_id; refresh_cart has no arguments."})
