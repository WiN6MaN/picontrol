"""scripts/personalize.sh: makes a downloaded copy of the project the user's own (names + commit authors)."""

import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pytestmark = pytest.mark.skipif(not shutil.which("git") or not shutil.which("bash"), reason="needs git and bash")
IDENTITY = ["-c", "user.name=Pi Control", "-c", "user.email=picontrol@users.noreply.github.com"]


def git(cwd, *args):
    return subprocess.run(["git"] + list(args), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)


@pytest.fixture
def repo(tmp_path):
    """A small synthetic project in pristine state (placeholders in place) with the real script and two commits.

    Independent of the state of the real working tree: it keeps working after the owner has run the script.
    """
    dest = str(tmp_path / "picontrol")
    files = {
        "README.md": "git clone https://github.com/<you>/picontrol.git\n",
        "README.fr.md": "git clone https://github.com/<vous>/picontrol.git\n",
        "CONTRIBUTING.md": "git clone https://github.com/<you>/picontrol.git\ngit clone https://github.com/<vous>/picontrol.git\n",
        "docs/en/installation.md": "git clone https://github.com/<you>/picontrol.git\n",
        "docs/fr/installation.md": "git clone https://github.com/<vous>/picontrol.git\n",
        "LICENSE": "MIT License\n\nCopyright (c) 2026 The Pi Control authors\n",
        "install.sh": "#!/bin/sh\n", "uninstall.sh": "#!/bin/sh\n", "scripts/common.sh": "#!/bin/sh\n",
    }
    for name, text in files.items():
        path = os.path.join(dest, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    shutil.copy(os.path.join(ROOT, "scripts", "personalize.sh"), os.path.join(dest, "scripts", "personalize.sh"))
    for name in ("install.sh", "uninstall.sh", "scripts/common.sh", "scripts/personalize.sh"):
        os.chmod(os.path.join(dest, name), 0o755)
    assert git(dest, "init", "-q", "-b", "main").returncode == 0
    for message, paths in (("Add code", ["install.sh", "uninstall.sh", "scripts"]), ("Add the rest", ["."])):
        git(dest, *IDENTITY, "add", *paths)
        assert git(dest, *IDENTITY, "commit", "-q", "-m", message).returncode == 0
    return dest


def run(repo, *args):
    return subprocess.run(["bash", os.path.join("scripts", "personalize.sh")] + list(args), cwd=repo, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)


def authors(repo):
    return set(git(repo, "log", "--format=%an <%ae> / %cn <%ce>").stdout.splitlines())


def test_personalizes_names_license_and_every_commit(repo):
    result = run(repo, "--github", "dede-retro", "--name", "Dédé Test", "--email", "123+dede@users.noreply.github.com")
    assert result.returncode == 0, result.stderr
    edited = ["README.md", "README.fr.md", "CONTRIBUTING.md", "docs/en/installation.md", "docs/fr/installation.md", "LICENSE"]
    for name in edited:  # no placeholder left in any file the script is responsible for
        text = open(os.path.join(repo, name), encoding="utf-8").read()
        assert "<you>" not in text and "<vous>" not in text, name
    assert "github.com/dede-retro/picontrol.git" in open(os.path.join(repo, "README.md"), encoding="utf-8").read()
    assert "Copyright (c) 2026 Dédé Test" in open(os.path.join(repo, "LICENSE"), encoding="utf-8").read()
    assert authors(repo) == {"Dédé Test <123+dede@users.noreply.github.com> / Dédé Test <123+dede@users.noreply.github.com>"}
    assert git(repo, "status", "--porcelain").stdout == ""
    assert "git remote add origin https://github.com/dede-retro/picontrol.git" in result.stdout
    assert git(repo, "log", "--oneline").stdout.count("\n") == 3  # the two commits + the owner commit; nothing lost


def test_can_be_run_again_with_another_identity(repo):
    assert run(repo, "--github", "first", "--name", "First", "--email", "a@b.co").returncode == 0
    assert run(repo, "--github", "first", "--name", "Second Name", "--email", "c@d.co").returncode == 0
    assert authors(repo) == {"Second Name <c@d.co> / Second Name <c@d.co>"}


def test_special_characters_in_the_name_are_safe(repo):
    name = "Dédé & Fils | Co \\ Ltd"
    assert run(repo, "--github", "ok", "--name", name, "--email", "a@b.co").returncode == 0
    assert "Copyright (c) 2026 %s" % name in open(os.path.join(repo, "LICENSE"), encoding="utf-8").read()


@pytest.mark.parametrize("args", [
    ["--github", "bad name", "--name", "X", "--email", "a@b.co"],
    ["--github", "-leading", "--name", "X", "--email", "a@b.co"],
    ["--github", "a" * 40, "--name", "X", "--email", "a@b.co"],
    ["--github", "ok", "--name", "X", "--email", "not-an-email"],
    ["--github", "ok", "--name", "", "--email", "a@b.co"],
    ["--github", "ok", "--name", "X"],  # no e-mail and no terminal to ask for it
    ["--bogus"],
])
def test_invalid_input_changes_nothing(repo, args):
    before = git(repo, "log", "--format=%H").stdout
    result = run(repo, *args)
    assert result.returncode != 0 and "ERROR" in result.stderr
    assert git(repo, "log", "--format=%H").stdout == before and git(repo, "status", "--porcelain").stdout == ""


def test_refuses_to_work_on_uncommitted_changes(repo):
    with open(os.path.join(repo, "README.md"), "a", encoding="utf-8") as handle:
        handle.write("\nmy edit\n")
    result = run(repo, "--github", "ok", "--name", "X", "--email", "a@b.co")
    assert result.returncode != 0 and "uncommitted" in result.stderr


def test_refuses_outside_a_git_repository(repo):
    shutil.rmtree(os.path.join(repo, ".git"))
    result = run(repo, "--github", "ok", "--name", "X", "--email", "a@b.co")
    assert result.returncode != 0 and "not a git repository" in result.stderr


def test_line_endings_are_pinned_to_lf():
    text = open(os.path.join(ROOT, ".gitattributes"), encoding="utf-8").read()
    assert "eol=lf" in text and "*.sh text eol=lf" in text


def test_environment_identity_does_not_leak_into_the_commits(repo):
    env = dict(os.environ, GIT_AUTHOR_NAME="Someone Else", GIT_AUTHOR_EMAIL="else@example.com",
               GIT_COMMITTER_NAME="Someone Else", GIT_COMMITTER_EMAIL="else@example.com")
    result = subprocess.run(["bash", os.path.join("scripts", "personalize.sh"), "--github", "ok", "--name", "Real Name",
                             "--email", "real@example.com"], cwd=repo, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    assert result.returncode == 0, result.stderr
    assert authors(repo) == {"Real Name <real@example.com> / Real Name <real@example.com>"}


def test_lost_executable_flags_do_not_count_as_changes(repo):
    for script in ("install.sh", "uninstall.sh", os.path.join("scripts", "common.sh")):
        os.chmod(os.path.join(repo, script), 0o644)  # what some zip tools do
    assert run(repo, "--github", "ok", "--name", "X Y", "--email", "a@b.co").returncode == 0
    listing = git(repo, "ls-files", "-s", "install.sh").stdout
    assert listing.startswith("100755") or listing.startswith("100644")  # the index is left as it was
