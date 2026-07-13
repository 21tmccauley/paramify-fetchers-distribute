"""Welcome-screen startup checks in the three content modes.

Regression for the readout failing on an installed (pipx/brew) copy: no
checkout on disk is the normal installed state, not a broken one — the
checks must answer from the catalog the app already loaded.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("textual")

from framework.tui.screens.welcome import WelcomeScreen  # noqa: E402

OK, MUTED, FAIL = 1, -1, -2


def resolve(root_path, catalog_data, manifests=()):
    fake = SimpleNamespace(
        app=SimpleNamespace(root_path=root_path, catalog_data=catalog_data),
        _manifests=list(manifests),
    )
    WelcomeScreen._resolve_checks(fake)
    return fake._check_results, fake._summary_parts


CAT = {"fetcher_count": 109, "categories": [{}] * 8,
       "roots": ["/install/framework/_bundled/fetchers"]}


def test_installed_mode_is_healthy():
    """No checkout + a loaded catalog = every check green (bundle mode)."""
    results, summary = resolve(None, CAT)
    assert results[0] == (OK, "✓ installed bundle")
    assert results[1][0] == OK and "109 fetchers" in results[1][1]
    assert results[3][0] == OK  # packaged uploader importable
    assert not any(state == FAIL for state, _ in results.values())
    assert "109 fetchers" in summary[0]


def test_installed_mode_with_user_dir_counts_roots():
    cat = dict(CAT, roots=["/home/u/.local/share/paramify/fetchers",
                           "/install/framework/_bundled/fetchers"])
    results, _ = resolve(None, cat)
    assert results[0] == (OK, "✓ installed · 2 roots")


def test_dev_checkout_shows_its_name():
    repo = Path(__file__).resolve().parents[1]
    results, _ = resolve(repo, CAT)
    assert results[0] == (OK, f"{repo.name}/")


def test_no_content_anywhere_still_fails():
    results, _ = resolve(None, None)
    assert results[0] == (FAIL, "✗ none found")
    assert results[1][0] == FAIL
