# =============================================================================
# WMO KODY POCASIA - preklad cisla na slovensky popis
# =============================================================================
# Open-Meteo API vracia pocasie ako cislo (WMO kod).
# Tento slovnik ho prelozi na citatelny text.
#
# Zdroj: https://open-meteo.com/en/docs#weathervariables
#
# Pouzitie:
#   from app.services.prediction_weather.weather_codes import WMO_CODES
#   popis = WMO_CODES.get(kod, "Neznamy")
# =============================================================================

WMO_CODES = {
    0: "Jasno",
    1: "Prevazne jasno",
    2: "Polojasno",
    3: "Zamracene",
    45: "Hmla",
    48: "Hmla s namrazou",
    51: "Mrholenie - slabe",
    53: "Mrholenie - mierne",
    55: "Mrholenie - silne",
    56: "Mrznuce mrholenie - slabe",
    57: "Mrznuce mrholenie - silne",
    61: "Dazd - slaby",
    63: "Dazd - mierny",
    65: "Dazd - silny",
    66: "Mrznuci dazd - slaby",
    67: "Mrznuci dazd - silny",
    71: "Snezenie - slabe",
    73: "Snezenie - mierne",
    75: "Snezenie - silne",
    77: "Snehove zrna",
    80: "Prehanky - slabe",
    81: "Prehanky - mierne",
    82: "Prehanky - silne",
    85: "Snehove prehanky - slabe",
    86: "Snehove prehanky - silne",
    95: "Burka",
    96: "Burka s malymi krupobitim",
    99: "Burka so silnym krupobitim",
}
