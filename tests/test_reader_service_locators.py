"""Discriminating test for the PDF locator admission path.

``external_sources._try_pymupdf4llm`` returns an *empty* locator list on
purpose: "an invented locator would sail past the admission check, whereas an
empty locator list makes the downstream admission fail closed." This test pins
that contract at the caller -- ``PaperReaderService._read_file`` must forward the
parser's empty locator list verbatim and must never fabricate a locator.
"""

from __future__ import annotations

from autoresearch.external_sources import ParseResult, ParseStatus
from autoresearch.reader_service import PaperReaderService

MARKDOWN = "# Parsed manuscript\n\nThe pymupdf4llm backend produced this markdown."


def test_ok_markdown_with_empty_locators_invents_no_locator(tmp_path, monkeypatch):
    pdf = tmp_path / "manuscript.pdf"
    pdf.write_bytes(b"%PDF-1.4 placeholder, parsing is monkeypatched")

    def _fake_parse(self, path_value):
        # Exactly the shape external_sources._try_pymupdf4llm returns: a rich
        # markdown body with no page locators available.
        return ParseResult(
            parser="pymupdf4llm",
            markdown=MARKDOWN,
            locators=[],
            status=ParseStatus.OK,
        )

    monkeypatch.setattr("autoresearch.reader_service.PdfParser.parse", _fake_parse)

    text, locators = PaperReaderService._read_file(str(pdf))

    assert text == MARKDOWN
    assert locators == []
