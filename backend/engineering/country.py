"""Country & regulatory context for an overseas bid.

Combines facts that are genuinely derivable from the site:

 * country / ISO code — from the Nominatim reverse geocode (real);
 * hemisphere — from latitude (real);
 * UTM zone + WGS84/UTM EPSG code — from longitude/latitude (real; used for
   setting-out and GIS);

with a small curated REFERENCE lookup of the likely design-code family,
currency and unit system per country. The reference items are flagged as
indicative — the governing code and currency for a contract must be confirmed
with the client and local authority. Nothing here is a site measurement, so
nothing is fabricated.
"""
from __future__ import annotations

from typing import Optional

from ..schemas import CountryContext, Location

# Countries that design to the Eurocodes (EU + EEA + UK/CH national annexes).
_EUROCODE = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE", "NO", "IS", "LI", "CH", "GB",
}
_EC_FAMILY = ("Eurocodes (EN 1990-1999)", "EN 1998-1 (Eurocode 8)",
              "EN 1991-1-4 / -1-3 (wind / snow)")

# Explicit non-Eurocode design-code families: (structural, seismic, wind/snow).
_CODE = {
    "US": ("ASCE 7 / IBC", "ASCE 7 (seismic)", "ASCE 7 (wind / snow)"),
    "CA": ("National Building Code of Canada", "NBC Part 4 (seismic)", "NBC Part 4"),
    "JP": ("Building Standard Law of Japan", "BSL seismic provisions", "BSL / AIJ"),
    "CN": ("GB national standards", "GB 50011 (seismic)", "GB 50009 (loads)"),
    "IN": ("IS codes (BIS)", "IS 1893 (seismic)", "IS 875 (wind)"),
    "AU": ("AS/NZS 1170 + AS 3600", "AS 1170.4 (earthquake)", "AS/NZS 1170.2 (wind)"),
    "NZ": ("AS/NZS 1170 + NZS 3101", "NZS 1170.5 (earthquake)", "AS/NZS 1170.2 / .3"),
    "ZA": ("SANS 10160", "SANS 10160-4 (seismic)", "SANS 10160-3 (wind)"),
    "BR": ("ABNT NBR", "NBR 15421 (seismic)", "NBR 6123 (wind)"),
    "EG": ("Egyptian Code (ECP)", "ECP 201 (loads / seismic)", "ECP 201 (wind)"),
    "AE": ("ASCE 7 / IBC + local (e.g. Dubai code)", "ASCE 7 (seismic)", "ASCE 7 (wind)"),
    "SA": ("Saudi Building Code (SBC)", "SBC 301 (seismic)", "SBC 301 (wind)"),
    "QA": ("QCS + ASCE 7 / IBC", "ASCE 7 (seismic)", "ASCE 7 (wind)"),
    "KW": ("ASCE 7 / IBC + local", "ASCE 7 (seismic)", "ASCE 7 (wind)"),
    "OM": ("ASCE 7 / IBC + local", "ASCE 7 (seismic)", "ASCE 7 (wind)"),
    "BH": ("ASCE 7 / IBC + local", "ASCE 7 (seismic)", "ASCE 7 (wind)"),
    "RU": ("SP (ex-SNiP) codes", "SP 14.13330 (seismic)", "SP 20.13330 (loads)"),
    "TR": ("TBDY 2018 / TS", "TBDY 2018 (seismic)", "TS 498 (loads)"),
    "MX": ("NTC / local (e.g. CDMX)", "NTC / MOC-CFE (seismic)", "NTC (wind)"),
}

# Reference currency (ISO 4217 + name) for common overseas-project countries.
_CURRENCY = {
    "US": "USD - US dollar", "GB": "GBP - Pound sterling", "EG": "EGP - Egyptian pound",
    "AE": "AED - UAE dirham", "SA": "SAR - Saudi riyal", "QA": "QAR - Qatari riyal",
    "KW": "KWD - Kuwaiti dinar", "OM": "OMR - Omani rial", "BH": "BHD - Bahraini dinar",
    "IN": "INR - Indian rupee", "CN": "CNY - Chinese yuan", "JP": "JPY - Japanese yen",
    "AU": "AUD - Australian dollar", "NZ": "NZD - NZ dollar", "ZA": "ZAR - Rand",
    "BR": "BRL - Brazilian real", "MX": "MXN - Mexican peso", "CA": "CAD - Canadian dollar",
    "RU": "RUB - Russian rouble", "TR": "TRY - Turkish lira", "NG": "NGN - Naira",
    "KE": "KES - Kenyan shilling", "MA": "MAD - Moroccan dirham", "DZ": "DZD - Algerian dinar",
    "ID": "IDR - Rupiah", "MY": "MYR - Ringgit", "SG": "SGD - Singapore dollar",
    "TH": "THB - Baht", "VN": "VND - Dong", "PH": "PHP - Philippine peso",
    "CH": "CHF - Swiss franc", "NO": "NOK - Norwegian krone", "SE": "SEK - Swedish krona",
    "PL": "PLN - Zloty", "RO": "RON - Leu", "LY": "LYD - Libyan dinar",
    "IQ": "IQD - Iraqi dinar", "JO": "JOD - Jordanian dinar", "PK": "PKR - Pakistani rupee",
    "BD": "BDT - Taka", "ET": "ETB - Birr", "TZ": "TZS - Tanzanian shilling",
    "GH": "GHS - Cedi", "AO": "AOA - Kwanza", "CL": "CLP - Chilean peso",
    "AR": "ARS - Argentine peso", "PE": "PEN - Sol", "CO": "COP - Colombian peso",
}
_EURO = {"AT", "BE", "HR", "CY", "EE", "FI", "FR", "DE", "GR", "IE", "IT", "LV",
         "LT", "LU", "MT", "NL", "PT", "SK", "SI", "ES"}
_IMPERIAL = {"US", "LR", "MM"}


def utm_zone(lat: float, lon: float) -> tuple[str, str]:
    """UTM zone label (e.g. '35N') and WGS84/UTM EPSG code for a coordinate."""
    zone = int((lon + 180.0) / 6.0) % 60 + 1
    north = lat >= 0
    epsg = (32600 if north else 32700) + zone
    return f"{zone}{'N' if north else 'S'}", f"EPSG:{epsg}"


def build_country_context(location: Location) -> Optional[CountryContext]:
    cc = (location.country_code or "").upper() or None
    lat, lon = location.lat, location.lon
    zone, epsg = utm_zone(lat, lon)

    ctx = CountryContext(
        country=location.country, country_code=cc,
        hemisphere="Northern" if lat >= 0 else "Southern",
        utm_zone=zone, epsg_code=epsg,
        source="Nominatim country + derived UTM/hemisphere + curated code/currency reference",
    )

    if cc in _EURO:
        ctx.currency = _CURRENCY.get(cc, "EUR - Euro")
    else:
        ctx.currency = _CURRENCY.get(cc)
    ctx.measurement_system = ("US customary units predominate (verify)"
                              if cc in _IMPERIAL else "Metric (SI)")

    if cc in _EUROCODE:
        fam = _EC_FAMILY
    else:
        fam = _CODE.get(cc)
    if fam:
        ctx.structural_code, ctx.seismic_code, ctx.wind_snow_code = fam
    else:
        ctx.notes.append("Design-code family not in the reference table — confirm the "
                         "contract's governing structural/seismic/wind code locally.")

    ctx.notes.append("Code, currency and units are INDICATIVE reference only — confirm the "
                     "governing standard and contract currency with the client/authority.")
    if cc not in _EUROCODE:
        ctx.notes.append("This tool's response spectrum is in Eurocode 8 format; map it to the "
                         "local seismic code above for design.")
    return ctx
