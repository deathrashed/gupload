import pytest

import gupload


# --- sanitize_repo_path (for --path override) ---

def test_sanitize_repo_path_basic():
    assert gupload.sanitize_repo_path("icons/wtfpl") == "icons/wtfpl"


def test_sanitize_repo_path_strips_leading_trailing_slashes():
    assert gupload.sanitize_repo_path("/icons/wtfpl/") == "icons/wtfpl"


def test_sanitize_repo_path_strips_whitespace():
    assert gupload.sanitize_repo_path("  icons/wtfpl  ") == "icons/wtfpl"


def test_sanitize_repo_path_collapses_double_slashes():
    assert gupload.sanitize_repo_path("icons//wtfpl") == "icons/wtfpl"


def test_sanitize_repo_path_strips_parent_traversal():
    assert gupload.sanitize_repo_path("../../etc/passwd") == "etc/passwd"


def test_sanitize_repo_path_strips_embedded_traversal():
    assert gupload.sanitize_repo_path("icons/../wtfpl") == "icons/wtfpl"


def test_sanitize_repo_path_empty_raises():
    with pytest.raises(ValueError):
        gupload.sanitize_repo_path("")


def test_sanitize_repo_path_only_traversal_raises():
    with pytest.raises(ValueError):
        gupload.sanitize_repo_path("../..")


# --- build_jsdelivr_url ---

def test_build_jsdelivr_url_basic():
    url = gupload.build_jsdelivr_url("deathrashed", "gupload", "main", "uploads/images/foo.png")
    assert url == "https://cdn.jsdelivr.net/gh/deathrashed/gupload@main/uploads/images/foo.png"


def test_build_jsdelivr_url_strips_leading_slash_on_path():
    url = gupload.build_jsdelivr_url("deathrashed", "gupload", "main", "/uploads/images/foo.png")
    assert url == "https://cdn.jsdelivr.net/gh/deathrashed/gupload@main/uploads/images/foo.png"


# --- render_formats ---

def test_render_formats_mdlink_non_image():
    lines, warnings = gupload.render_formats(
        ["mdlink"], "foo.mp3", "https://example.com/foo.mp3",
        is_image=False, is_audio=False,
    )
    assert lines == ["[foo.mp3](https://example.com/foo.mp3)"]
    assert warnings == []


def test_render_formats_mdimage():
    lines, warnings = gupload.render_formats(
        ["mdimage"], "foo.png", "https://example.com/foo.png",
        is_image=True, is_audio=False,
    )
    assert lines == ["![foo.png](https://example.com/foo.png)"]


def test_render_formats_literal():
    lines, warnings = gupload.render_formats(
        ["literal"], "foo.png", "https://example.com/foo.png",
        is_image=True, is_audio=False,
    )
    assert lines == ["https://example.com/foo.png"]


def test_render_formats_html_image():
    lines, warnings = gupload.render_formats(
        ["html"], "foo.png", "https://example.com/foo.png",
        is_image=True, is_audio=False,
    )
    assert lines == ['<img src="https://example.com/foo.png">']


def test_render_formats_html_audio():
    lines, warnings = gupload.render_formats(
        ["html"], "foo.mp3", "https://example.com/foo.mp3",
        is_image=False, is_audio=True,
    )
    assert lines == ['<audio controls src="https://example.com/foo.mp3"></audio>']


def test_render_formats_html_other():
    lines, warnings = gupload.render_formats(
        ["html"], "foo.zip", "https://example.com/foo.zip",
        is_image=False, is_audio=False,
    )
    assert lines == ['<a href="https://example.com/foo.zip">foo.zip</a>']


def test_render_formats_jsdelivr_available():
    lines, warnings = gupload.render_formats(
        ["jsdelivr"], "foo.png", "https://example.com/foo.png",
        is_image=True, is_audio=False,
        jsdelivr_url="https://cdn.jsdelivr.net/gh/o/r@main/uploads/images/foo.png",
    )
    assert lines == ["https://cdn.jsdelivr.net/gh/o/r@main/uploads/images/foo.png"]
    assert warnings == []


def test_render_formats_jsdelivr_unavailable_warns_and_skips():
    lines, warnings = gupload.render_formats(
        ["jsdelivr"], "foo.png", "https://example.com/foo.png",
        is_image=True, is_audio=False,
        jsdelivr_url=None,
    )
    assert lines == []
    assert len(warnings) == 1
    assert "jsdelivr" in warnings[0].lower()


def test_render_formats_multiple_in_order():
    lines, warnings = gupload.render_formats(
        ["mdlink", "literal"], "foo.zip", "https://example.com/foo.zip",
        is_image=False, is_audio=False,
    )
    assert lines == [
        "[foo.zip](https://example.com/foo.zip)",
        "https://example.com/foo.zip",
    ]


# --- lowercase rendering helpers ---

def test_commit_message_for_lowercases_category():
    assert gupload.commit_message_for("Audio", "foo.mp3") == "audio ⋅ foo.mp3"


def test_release_prefix_for_lowercases_category():
    assert gupload.release_prefix_for("Images", "foo") == "images-foo"


# --- category_from_magic / category_for_path extensionless fallback ---

def test_category_from_magic_returns_none_without_extension_match(tmp_path):
    f = tmp_path / "noext"
    f.write_bytes(b"plain text content, no shebang here\n")
    # text/plain should map to Documents via the magic fallback.
    cat = gupload.category_from_magic(str(f))
    assert cat in ("Documents", None)  # None only if libmagic unavailable in this env


def test_category_for_path_extensionless_shebang_still_works(tmp_path, monkeypatch):
    # Force category_from_magic to miss, so the shebang fallback is exercised.
    monkeypatch.setattr(gupload, "category_from_magic", lambda path: None)
    f = tmp_path / "myscript"
    f.write_bytes(b"#!/bin/bash\necho hi\n")
    assert gupload.category_for_path(str(f)) == "Scripts"


def test_category_for_path_extensionless_no_shebang_no_magic_is_other(tmp_path, monkeypatch):
    monkeypatch.setattr(gupload, "category_from_magic", lambda path: None)
    f = tmp_path / "mystery"
    f.write_bytes(b"random binary junk \x00\x01\x02")
    assert gupload.category_for_path(str(f)) == "Other"


# --- taxonomy rules -------------------------------------------------------

def test_taxonomy_license_files():
    assert gupload.taxonomy_path_for({}, "/x/LICENSE") == "files/licenses"
    assert gupload.taxonomy_path_for({}, "/x/License.txt") == "files/licenses"
    assert gupload.taxonomy_path_for({}, "/x/license-mit.md") is None


def test_taxonomy_icon_extensions():
    assert gupload.taxonomy_path_for({}, "/x/app.ICNS") == "icons"


def test_taxonomy_user_rules_win_and_lowercase():
    cfg = {"taxonomy_rules": [{"match": r"^docker-", "path": "Icons/Docker/"}]}
    assert gupload.taxonomy_path_for(cfg, "docker-logo.svg") == "icons/docker"


def test_build_repo_path_uses_taxonomy(tmp_path):
    f = tmp_path / "LICENSE"
    f.write_text("MIT")
    path, _ = gupload.build_repo_path({"dedup_strategy": "none"}, str(f))
    assert path == "uploads/files/licenses/LICENSE"
