import pytest
from pydantic import ValidationError

from backend.engineering.rf import summarize_rf_survey
from backend.report.pdf import build_pdf
from backend.schemas import (Assessment, GeotechParameters, Location, RfSurveyRequest,
                             SeismicContext, SoilProfile, Terrain)


def test_rf_survey_summary_preserves_imported_measurement_basis():
    survey = RfSurveyRequest(
        authorized_receiver=True,
        receiver_name="Authorised field receiver",
        captured_utc="2026-11-03T10:30:00Z",
        occupancy_threshold_dbm=-85,
        readings=[
            {"frequency_mhz": 88.5, "power_dbm": -97.0},
            {"frequency_mhz": 98.1, "power_dbm": -72.4},
            {"frequency_mhz": 102.3, "power_dbm": -84.9},
        ],
    )

    summary = summarize_rf_survey(survey)

    assert summary is not None
    assert summary.frequency_low_mhz == 88.5
    assert summary.frequency_high_mhz == 102.3
    assert summary.sample_count == 3
    assert summary.occupied_sample_count == 2
    assert summary.peak_frequency_mhz == 98.1
    assert summary.peak_power_dbm == -72.4
    assert "does not detect every radio service" in summary.note


def test_rf_survey_requires_authorized_receiver_confirmation():
    with pytest.raises(ValidationError):
        RfSurveyRequest(
            authorized_receiver=False,
            readings=[{"frequency_mhz": 100, "power_dbm": -80}],
        )


def test_rf_survey_summary_is_included_in_pdf_report():
    summary = summarize_rf_survey(RfSurveyRequest(
        authorized_receiver=True,
        readings=[{"frequency_mhz": 100, "power_dbm": -80}],
    ))
    assessment = Assessment(
        project_name="RF Test",
        generated_utc="2026-11-03 10:30 UTC",
        location=Location(lat=1.4, lon=31.1),
        terrain=Terrain(),
        soil=SoilProfile(),
        seismic=SeismicContext(search_radius_km=300),
        parameters=GeotechParameters(),
        rf_survey=summary,
    )

    pdf = build_pdf(assessment)

    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 3000
