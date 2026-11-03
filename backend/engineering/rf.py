"""Summarise user-supplied, non-content RF spectrum readings.

This module deliberately does not interface with SDRs, tune receivers, decode
signals, record audio, or infer the identity/location of transmitters.  It
only summarises the frequency/power values an authorised user imported.
"""
from __future__ import annotations

from ..schemas import RfSurveyRequest, RfSurveySummary


def summarize_rf_survey(survey: RfSurveyRequest | None) -> RfSurveySummary | None:
    """Return a transparent summary, preserving the imported-scan limitation."""
    if survey is None or not survey.readings:
        return None

    readings = survey.readings
    peak = max(readings, key=lambda item: item.power_dbm)
    low = min(item.frequency_mhz for item in readings)
    high = max(item.frequency_mhz for item in readings)
    occupied = sum(item.power_dbm >= survey.occupancy_threshold_dbm for item in readings)
    count = len(readings)

    return RfSurveySummary(
        receiver_name=survey.receiver_name or None,
        captured_utc=survey.captured_utc or None,
        frequency_low_mhz=round(low, 6),
        frequency_high_mhz=round(high, 6),
        sample_count=count,
        occupancy_threshold_dbm=survey.occupancy_threshold_dbm,
        occupied_sample_count=occupied,
        occupied_percent=round((occupied / count) * 100, 1),
        peak_frequency_mhz=round(peak.frequency_mhz, 6),
        peak_power_dbm=round(peak.power_dbm, 1),
        source="User-imported spectrum power readings from an authorised receiver",
        note=(
            "Non-content RF spectrum survey only. It reports imported frequency/power "
            "samples; it does not detect every radio service, identify transmitters, "
            "or capture communications."
        ),
    )
