import pytest

try:
    from devtools.flash import fla
    STOCK = fla.FLARE_DIR / "fla" / "STK_C23_Princess_Twilight_Sparkle.fla"
except ImportError:  # FLA-RE not available
    STOCK = None


@pytest.fixture(scope="session")
def twilight_library(tmp_path_factory):
    """Princess Twilight imported once per test session (2 px per unit, for speed)."""
    if STOCK is None or not STOCK.exists():
        pytest.skip("Princess Twilight stock file not available")
    from devtools.flash.import_character import import_character
    out = tmp_path_factory.mktemp("twilight")
    import_character(STOCK, "~PTS_Character", "twilight", out, ppu=2.0, jobs=6)
    return out
