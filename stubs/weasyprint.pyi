"""Minimal typing stub for the parts of WeasyPrint this project uses.

WeasyPrint ships no py.typed marker and there is no types-weasyprint on PyPI,
so mypy would otherwise treat the import as untyped. Only the constructor
keywords and the write_pdf return type we actually rely on are declared; add
more here as usage grows rather than widening the whole module to Any.
"""

from typing import Any

class HTML:
    def __init__(
        self,
        guess: Any | None = ...,
        filename: str | None = ...,
        url: str | None = ...,
        file_obj: Any | None = ...,
        string: str | None = ...,
        encoding: str | None = ...,
        base_url: str | None = ...,
        url_fetcher: Any | None = ...,
        media_type: str = ...,
    ) -> None: ...
    def write_pdf(self, target: Any | None = ..., **options: Any) -> bytes: ...
