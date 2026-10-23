"""Shared test-only tracing; never serialize client credentials or reasoning."""
import json
import httpx
from pydantic import BaseModel
from time import perf_counter
from datetime import datetime, timezone


def _structured_argument(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    raise TypeError("Unsupported evaluation argument type")


class RecordedClient:
    """Record explicit method arguments/results, never client settings or headers."""
    def __init__(self, client, records, methods, component=None):
        self.client, self.records, self.methods = client, records, methods
        self.component = component

    def __getattr__(self, name):
        method = getattr(self.client, name)
        if name not in self.methods:
            return method

        def recorded(*args, **kwargs):
            row = {"operation": name, "input": {"args": args, "kwargs": kwargs}}
            if self.component:
                row["component"] = self.component
            # Freeze inputs before a JSON repair mutates its message list.
            row["input"] = json.loads(json.dumps(row["input"], default=_structured_argument))
            self.records.append(row)
            row['started_at'] = datetime.now(timezone.utc).isoformat()
            started = perf_counter()
            try:
                result = method(*args, **kwargs)
                # Exclude model reasoning and transport metadata.
                row["output"] = ({"content": result.get("message", {}).get("content")}
                                 if name == "chat" else result)
                if name == "chat":
                    row["usage"] = {"input_tokens": result.get("prompt_eval_count"),
                                    "output_tokens": result.get("eval_count")}
                row["status"] = "ok"
                return result
            except Exception as exc:
                # Exception messages may contain request URLs or credentials.
                row.update(status="error", error_type=type(exc).__name__)
                if isinstance(exc, httpx.HTTPStatusError):
                    row["http_status"] = exc.response.status_code
                    row["endpoint_path"] = exc.request.url.path
                    # Validation locations reveal malformed fields without echoing inputs.
                    try:
                        detail = exc.response.json().get("detail", [])
                        if isinstance(detail, list):
                            row["validation_errors"] = [
                                {"location": e.get("loc"), "type": e.get("type")}
                                for e in detail if isinstance(e, dict)]
                    except (ValueError, AttributeError):
                        pass
                raise
            finally:
                row["duration_seconds"] = round(perf_counter() - started, 4)
                row['ended_at'] = datetime.now(timezone.utc).isoformat()
        return recorded

