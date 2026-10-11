import re
import unicodedata


def normalize_text(text):
    return " ".join(unicodedata.normalize("NFKC", text or "").split())


def keyword_query(text):
    """Quote tokens so user input cannot act as FTS syntax."""
    tokens = list(dict.fromkeys(re.findall(r"[^\W_]+", normalize_text(text).lower())))
    return " OR ".join('"' + token + '"' for token in tokens)
