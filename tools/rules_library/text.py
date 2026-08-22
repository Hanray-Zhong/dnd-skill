from __future__ import annotations

import re


def normalized_text(text: str) -> str:
    normalized = " ".join(text.replace("\u00a0", " ").split())
    normalized = re.sub(
        r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])",
        "",
        normalized,
    )
    normalized = re.sub(r"\s+([，。；：、？！）》】])", r"\1", normalized)
    normalized = re.sub(r"([（《【])\s+", r"\1", normalized)
    return normalized.strip()


def lookup_key(text: str) -> str:
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE).casefold()


def title_aliases(title: str) -> tuple[str, ...]:
    aliases = [title]
    english_start = re.search(r"[A-Za-z]", title)
    if english_start is not None:
        chinese = title[: english_start.start()].strip(" ：:，,、")
        english = title[english_start.start() :].strip()
        english = re.split(r"\s+(?:[0-9０-９]+\s*[环级换]|戏法)\b", english)[0]
        if chinese:
            aliases.append(chinese)
        if english:
            aliases.append(english)
    return tuple(dict.fromkeys(alias for alias in aliases if alias))
