"""
Unit tests for the _detect_undercut() algorithm in backend/routers/strategy.py.

This is pure Python logic with no external dependencies — no mocking needed.
"""
import pytest

from backend.routers.strategy import _detect_undercut


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Driver post-pit laps: pit_lap+1 .. pit_lap+3
# Competitor comparison laps: pit_lap .. pit_lap+2


def _lap_times(driver_times: dict, comp_times: dict, pit_lap: int = 5):
    """
    Build a lap_times dict with driver laps starting at pit_lap+1
    and competitor laps starting at pit_lap.
    """
    return {
        "DRV": {pit_lap + 1 + i: t for i, t in enumerate(driver_times)},
        "CMP": {pit_lap + i: t for i, t in enumerate(comp_times)},
    }


# ---------------------------------------------------------------------------
# Undercut Success
# ---------------------------------------------------------------------------


def test_undercut_success_gained_position_and_faster():
    """Driver pitted, emerged ahead, and posted faster average lap times."""
    pit_lap = 5
    lap_times = _lap_times([89.0, 88.5, 88.0], [91.0, 91.5, 92.0], pit_lap)
    pos_before = {"DRV": 3, "CMP": 2}   # DRV was behind CMP
    pos_after = {"DRV": 2, "CMP": 3}    # DRV jumped ahead

    label, explanation = _detect_undercut("DRV", pit_lap, lap_times, pos_before, pos_after)

    assert label == "Undercut Success"
    assert "DRV" in explanation
    assert str(pit_lap) in explanation


# ---------------------------------------------------------------------------
# Overcut Success
# ---------------------------------------------------------------------------


def test_overcut_success_gained_position_but_not_faster():
    """Driver gained position via strategy without being faster on fresh tyres."""
    pit_lap = 5
    # DRV laps (92–91) are slower than CMP (91–90): avg_driver > avg_comp
    lap_times = _lap_times([92.0, 92.0, 92.0], [91.0, 91.0, 91.0], pit_lap)
    pos_before = {"DRV": 3, "CMP": 2}
    pos_after = {"DRV": 2, "CMP": 3}

    label, explanation = _detect_undercut("DRV", pit_lap, lap_times, pos_before, pos_after)

    assert label == "Overcut Success"


# ---------------------------------------------------------------------------
# Undercut Failed
# ---------------------------------------------------------------------------


def test_undercut_failed_competitor_gained_position_and_was_faster():
    """Competitor maintained / gained position and was faster."""
    pit_lap = 5
    # DRV slower, CMP faster
    lap_times = _lap_times([91.0, 91.5, 92.0], [90.0, 89.5, 89.0], pit_lap)
    pos_before = {"DRV": 2, "CMP": 3}   # DRV was ahead of CMP
    pos_after = {"DRV": 3, "CMP": 2}    # CMP jumped ahead (undercut failed)

    label, explanation = _detect_undercut("DRV", pit_lap, lap_times, pos_before, pos_after)

    assert label == "Undercut Failed"
    assert "DRV" in explanation


# ---------------------------------------------------------------------------
# Neutral — no nearby competitors
# ---------------------------------------------------------------------------


def test_neutral_empty_positions():
    label, explanation = _detect_undercut("DRV", 5, {}, {}, {})
    assert label == "Neutral"
    assert "No nearby competitors" in explanation


def test_neutral_competitor_more_than_3_positions_away():
    """Drivers > 3 positions apart are not counted as nearby."""
    pos_before = {"DRV": 1, "CMP": 10}   # 9 positions apart
    pos_after = {"DRV": 1, "CMP": 10}

    label, explanation = _detect_undercut("DRV", 5, {}, pos_before, pos_after)

    assert label == "Neutral"
    assert "No nearby competitors" in explanation


def test_neutral_exactly_3_positions_away_is_nearby():
    """Drivers exactly 3 positions apart ARE considered nearby (abs(p - pos_before) <= 3)."""
    pit_lap = 5
    lap_times = _lap_times([89.0, 89.0, 89.0], [91.0, 91.0, 91.0], pit_lap)
    pos_before = {"DRV": 4, "CMP": 1}   # exactly 3 apart
    pos_after = {"DRV": 3, "CMP": 2}

    label, _ = _detect_undercut("DRV", pit_lap, lap_times, pos_before, pos_after)

    # Should NOT be neutral (competitor was nearby)
    assert label != "Neutral" or "No nearby competitors" not in _


# ---------------------------------------------------------------------------
# Neutral — no lap time data
# ---------------------------------------------------------------------------


def test_neutral_no_lap_times_for_driver():
    """When lap_times is empty, we fall through to Neutral."""
    pos_before = {"DRV": 2, "CMP": 3}
    pos_after = {"DRV": 2, "CMP": 3}

    label, explanation = _detect_undercut("DRV", 5, {}, pos_before, pos_after)

    assert label == "Neutral"


def test_neutral_position_unchanged():
    """When position is unchanged and no classification matches, result is Neutral."""
    pit_lap = 5
    # Both drive same pace — neither gained position
    lap_times = {
        "DRV": {6: 91.0, 7: 91.0, 8: 91.0},
        "CMP": {5: 91.0, 6: 91.0, 7: 91.0},
    }
    pos_before = {"DRV": 3, "CMP": 4}
    pos_after = {"DRV": 3, "CMP": 4}   # No change

    label, _ = _detect_undercut("DRV", pit_lap, lap_times, pos_before, pos_after)

    assert label == "Neutral"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_driver_not_in_positions():
    """Driver missing from both position dicts defaults to pos 99 — no position gain."""
    pit_lap = 5
    lap_times = {
        "DRV": {6: 89.0},
        "CMP": {5: 91.0},
    }
    # DRV not in positions → defaults to 99 vs 99 → no change
    label, _ = _detect_undercut("DRV", pit_lap, lap_times, {"CMP": 2}, {"CMP": 2})
    # pos_before(DRV)=99, pos_after(DRV)=99 → neither gained → Neutral
    assert label == "Neutral"


def test_only_one_nearby_competitor_considered():
    """With one nearby and one far competitor, only the nearby one matters."""
    pit_lap = 5
    lap_times = {
        "DRV": {6: 89.0, 7: 89.0, 8: 89.0},
        "NEAR": {5: 91.0, 6: 91.0, 7: 91.0},
        "FAR": {5: 85.0, 6: 85.0, 7: 85.0},
    }
    pos_before = {"DRV": 3, "NEAR": 2, "FAR": 15}
    pos_after = {"DRV": 2, "NEAR": 3, "FAR": 15}

    label, explanation = _detect_undercut("DRV", pit_lap, lap_times, pos_before, pos_after)

    assert label == "Undercut Success"
    # FAR is 12 positions away — should not appear in explanation
    assert "FAR" not in explanation
