from __future__ import annotations

import pytest

from core.language_completion import (
    CompletionItem, CompletionQuery, CompletionTextEdit, CompletionRegistry,
    completion_edit_plan, completion_query, text_offset_to_utf16, utf16_offset_to_text,
)
from core.lsp_features import completion_query_from_lsp_items, normalize_completion_items


def _apply(text, query, item):
    edits, caret = completion_edit_plan(text, query, item)
    for edit in edits:
        text = text[:edit.start] + edit.new_text + text[edit.end:]
    return text, caret


@pytest.mark.parametrize("language,text,label", [
    ("Java", 'class Demo { String name = "😀"; void run() { System.out.pr', "println()"),
    ("Python", 'name = "😀"\npri', "print"),
    ("C++", 'const char* face = "😀"; std::vector<int> items; items.pu', "push_back()"),
    ("JavaScript", 'const face = "😀"; console.lo', "log()"),
    ("HTML", '<p>😀</p>\n<but', "button"),
    ("CSS", '/* 😀 */ .panel { dis', "display"),
])
def test_all_visible_languages_preserve_unicode_prefix_when_accepting(language, text, label):
    qt_offset = text_offset_to_utf16(text, len(text))
    python_offset = utf16_offset_to_text(text, qt_offset)
    query = completion_query(language, text, python_offset)
    assert query is not None
    item = next(item for item in query.items if item.label == label)
    changed, caret = _apply(text, query, item)
    assert "😀" in changed
    assert changed[:query.start] == text[:query.start]
    assert changed[query.start:].startswith(item.insert_text)
    assert 0 <= caret <= len(changed)


def test_unicode_query_does_not_consume_following_newline():
    text = 'name = "😀"\npri\nnext_line = 1'
    offset = text.index("pri") + 3
    query = completion_query("Python", text, utf16_offset_to_text(text, text_offset_to_utf16(text, offset)))
    item = next(item for item in query.items if item.label == "print")
    changed, _ = _apply(text, query, item)
    assert changed == 'name = "😀"\nprint()\nnext_line = 1'


@pytest.mark.parametrize("text", ['description = """\npri', "description = '''\npri", '# comment\n"unterminated pri'])
def test_python_completion_is_suppressed_inside_multiline_strings(text):
    assert completion_query("Python", text, len(text)) is None


def test_python_completion_resumes_after_docstring_and_keeps_hash_in_strings():
    text = 'description = """# example\ntext\n"""\npri'
    assert any(item.label == "print" for item in completion_query("Python", text, len(text)).items)


def test_html_completion_does_not_offer_tags_inside_comments():
    assert completion_query("HTML", '<!-- note\n<di', 15) is None


def test_javascript_template_literal_is_not_treated_as_code():
    text = "const message = `line one\nconsole.lo"
    assert completion_query("JavaScript", text, len(text)) is None


def test_css_url_slashes_do_not_start_a_line_comment():
    text = ".panel { background: url(https://example.test/image.png); dis"
    query = completion_query("CSS", text, len(text))
    assert query is not None and any(item.label == "display" for item in query.items)


def test_manual_offline_completion_accepts_a_single_character_prefix():
    assert completion_query("Python", "p", 1) is None
    assert any(item.label == "print" for item in completion_query("Python", "p", 1, manual=True).items)


def test_registry_keeps_two_argument_custom_provider_contract():
    class Provider:
        def complete(self, text, offset):
            return CompletionQuery(offset, offset, "", (CompletionItem("custom", "custom", "", "symbol"),))
    registry = CompletionRegistry()
    registry.register("Custom", Provider())
    assert registry.complete("Custom", "", 0, manual=True).items[0].label == "custom"


def _range(line, start, end):
    return {"start": {"line": line, "character": start}, "end": {"line": line, "character": end}}


def test_lsp_insert_replace_and_dependency_import_form_one_edit_transaction():
    text = 'face = "😀"\nPathtail'
    response = [{
        "label": "Path",
        "textEdit": {"insert": _range(1, 0, 2), "replace": _range(1, 0, 8), "newText": "Path"},
        "additionalTextEdits": [{"range": _range(0, 0, 0), "newText": "from pathlib import Path\n"}],
    }]
    query = completion_query_from_lsp_items(text, text.index("Pathtail") + 2, normalize_completion_items(response))
    changed, caret = _apply(text, query, query.items[0])
    assert changed == 'from pathlib import Path\nface = "😀"\nPath'
    assert caret == len(changed)


def test_lsp_empty_new_text_deletes_the_selected_range():
    response = [{"label": "print", "textEdit": {"range": _range(0, 0, 3), "newText": ""}}]
    query = completion_query_from_lsp_items("pri", 3, normalize_completion_items(response))
    assert _apply("pri", query, query.items[0]) == ("", 0)


@pytest.mark.parametrize("edits", [
    [{"range": _range(20, 0, 0), "newText": "import unrelated\n"}],
    [{"range": _range(0, 1, 2), "newText": "x"}],
    [{"range": _range(1, 0, 1), "newText": "x"}],
])
def test_lsp_invalid_or_overlapping_edits_reject_the_entire_item(edits):
    text = "😀\npri"
    response = [{"label": "print", "textEdit": {"range": _range(1, 0, 3), "newText": "print"}, "additionalTextEdits": edits}]
    assert completion_query_from_lsp_items(text, len(text), normalize_completion_items(response)) is None


def test_lsp_filter_text_may_differ_from_display_label():
    response = [{"label": "λ lambda", "filterText": "lambda", "insertText": "lambda"}]
    query = completion_query_from_lsp_items("lam", 3, normalize_completion_items(response))
    assert query.items[0].label == "λ lambda"
    assert _apply("lam", query, query.items[0])[0] == "lambda"


def test_server_snippets_are_not_inserted_as_literal_placeholder_source():
    assert normalize_completion_items([{"label": "function", "insertText": "function(${1:name})", "insertTextFormat": 2}]) == []


def test_overlapping_builtin_import_and_replacement_are_rejected():
    item = CompletionItem("bad", "print", "", "symbol", (CompletionTextEdit(1, 3, "x"),))
    with pytest.raises(ValueError):
        completion_edit_plan("pri", CompletionQuery(0, 3, "pri", (item,)), item)
