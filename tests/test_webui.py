"""Static checks on the browser code: no HTML injection primitives, nothing the CSP would block."""

import os
import re
import shutil
import subprocess

import pytest

UI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "picontrol", "webui")


def read(name):
    with open(os.path.join(UI, name), encoding="utf-8") as handle:
        return handle.read()


def code(name):
    """The file without comments, so a comment may mention what the code must not do."""
    text = re.sub(r"/\*.*?\*/", "", read(name), flags=re.S)
    return re.sub(r"(?m)^\s*//.*$|\s//\s.*$", "", text)


def translation_keys(block):
    """Property names of one language block (string contents are blanked first: they may contain colons)."""
    blanked = re.sub(r'"(?:[^"\\]|\\.)*"', '""', block)
    return set(re.findall(r"\b(\w+):", blanked))


@pytest.mark.parametrize("pattern", [r"innerHTML", r"outerHTML", r"insertAdjacentHTML", r"document\.write", r"\beval\s*\(",
                                     r"new\s+Function", r"setTimeout\s*\(\s*['\"]", r"javascript:", r"\.srcdoc"])
def test_app_js_has_no_html_injection_primitives(pattern):
    assert not re.search(pattern, code("app.js")), pattern


def test_page_has_no_inline_code_or_styles():
    html = read("index.html")
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html)  # only external scripts
    assert not re.search(r"\bon\w+\s*=", html) and "style=" not in html and "<style" not in html
    assert "https://" not in html and "http://" not in html  # nothing loaded from elsewhere


def test_javascript_never_sets_inline_styles():
    assert "setAttribute(\"style\"" not in code("app.js") and ".style." not in code("app.js")


def language_blocks():
    js = read("app.js")
    return {lang: re.search(r"\n    %s: \{(.*?)\n    \}," % lang, js, re.S).group(1) for lang in ("en", "fr")}


def test_both_languages_have_the_same_keys():
    blocks = language_blocks()
    en, fr = translation_keys(blocks["en"]), translation_keys(blocks["fr"])
    assert en == fr and len(en) > 50, (en ^ fr)


def test_every_translation_key_used_in_the_code_exists():
    js = code("app.js")
    defined = translation_keys(language_blocks()["en"])
    used = set(re.findall(r"\bt\(\"(\w+)\"\)", js)) | set(re.findall(r"\[\"\w+\", \"(tab\w+)\"", js))
    assert used and used - defined == set()


def test_no_translation_is_left_untranslated():
    blocks = language_blocks()
    pairs = zip(re.findall(r'(\w+): "((?:[^"\\]|\\.)*)"', blocks["en"]), re.findall(r'(\w+): "((?:[^"\\]|\\.)*)"', blocks["fr"]))
    same = [k for (k, en), (_, fr) in pairs if en == fr and en not in ("Pi Control", "Version", "UID", "ON", "OFF", "ROM", "LED")]
    assert same == []


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_javascript_syntax():
    subprocess.check_call(["node", "--check", os.path.join(UI, "app.js")])
