"""Keeps the bilingual documentation honest: same files, same structure, working links."""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
LINK = re.compile(r"\]\(([^)#\s]*)(?:#([^)\s]*))?\)")


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def headings(text):
    in_code, found = False, []
    for line in text.splitlines():
        if line.startswith("```"):
            in_code = not in_code
        elif not in_code and re.match(r"#{1,6} ", line):
            found.append(line)
    return found


def slug(heading):
    text = re.sub(r"^#+\s*", "", heading).strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s", "-", text)


def md_files():
    out = [os.path.join(ROOT, name) for name in os.listdir(ROOT) if name.endswith(".md")]
    for lang in ("en", "fr"):
        out += [os.path.join(DOCS, lang, name) for name in os.listdir(os.path.join(DOCS, lang))]
    return out


def test_both_languages_have_the_same_pages():
    assert sorted(os.listdir(os.path.join(DOCS, "en"))) == sorted(os.listdir(os.path.join(DOCS, "fr")))


def test_translated_pages_have_the_same_structure():
    for name in os.listdir(os.path.join(DOCS, "en")):
        en, fr = read(os.path.join(DOCS, "en", name)), read(os.path.join(DOCS, "fr", name))
        assert len(headings(en)) == len(headings(fr)), name
        assert en.count("```") == fr.count("```"), name
        assert en.count("\n|") == fr.count("\n|"), "table rows differ in " + name


def test_readmes_mirror_each_other():
    en, fr = read(os.path.join(ROOT, "README.md")), read(os.path.join(ROOT, "README.fr.md"))
    assert len(headings(en)) == len(headings(fr))
    assert en.count("\n|") == fr.count("\n|")


def test_relative_links_and_anchors_resolve():
    for path in md_files():
        text = read(path)
        for target, anchor in LINK.findall(text):
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
            assert os.path.exists(resolved), "%s links to missing %s" % (os.path.relpath(path, ROOT), target)
            if anchor and resolved.endswith(".md"):
                slugs = [slug(h) for h in headings(read(resolved))]
                assert anchor in slugs, "%s: no heading for #%s in %s" % (os.path.relpath(path, ROOT), anchor, target)


def test_every_documented_command_exists():
    from picontrol import cli
    parser_help = cli.build_parser().format_help()
    for command in ("run", "tag", "test", "doctor"):
        assert command in parser_help
