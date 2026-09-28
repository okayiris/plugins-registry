"""Sample answers shaped like the NS Reisinformatie API (https://apiportal.ns.nl), for recording a cassette
without a key. Record with IRIS_KEY_NS set to replace them with real answers."""
from datetime import datetime, timedelta


def answer(item, method, url, body):
    now = datetime.now().astimezone().replace(second=0, microsecond=0)
    iso = lambda m: (now + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%S%z")
    if "v2/stations" in url:
        return 200, {"payload": [
            {"code": "UT", "namen": {"lang": "Utrecht Centraal", "middel": "Utrecht C.", "kort": "Utrecht C"}, "land": "NL", "synoniemen": []},
            {"code": "UTO", "namen": {"lang": "Utrecht Overvecht", "middel": "Overvecht", "kort": "Overvecht"}, "land": "NL", "synoniemen": []},
            {"code": "ASD", "namen": {"lang": "Amsterdam Centraal", "middel": "Amsterdam C.", "kort": "Amsterdam"}, "land": "NL", "synoniemen": ["Amsterdam CS"]},
            {"code": "GVC", "namen": {"lang": "Den Haag Centraal", "middel": "Den Haag C.", "kort": "Den Haag C"}, "land": "NL", "synoniemen": ["The Hague"]},
            {"code": "ZL", "namen": {"lang": "Zwolle", "middel": "Zwolle", "kort": "Zwolle"}, "land": "NL", "synoniemen": []}]}
    if "departures" in url:
        return 200, {"payload": {"departures": [
            {"direction": "Amsterdam Centraal", "plannedDateTime": iso(4), "actualDateTime": iso(7), "plannedTrack": "5",
             "actualTrack": "7", "product": {"shortCategoryName": "IC"}, "cancelled": False,
             "messages": [{"message": "Let op, gewijzigd vertrekspoor", "style": "WARNING"}]},
            {"direction": "Zwolle", "plannedDateTime": iso(9), "actualDateTime": iso(9), "plannedTrack": "11",
             "product": {"shortCategoryName": "SPR"}, "cancelled": True, "messages": []}]}}
    if "v3/trips" in url:
        def leg(o, d, a, b, track):
            return {"origin": {"name": o, "plannedDateTime": iso(a), "actualDateTime": iso(a + 2), "plannedTrack": track},
                    "destination": {"name": d, "plannedDateTime": iso(b), "plannedTrack": "3"}, "cancelled": False}
        return 200, {"trips": [
            {"plannedDurationInMinutes": 27, "transfers": 0, "status": "NORMAL",
             "legs": [leg("Utrecht Centraal", "Amsterdam Centraal", 4, 31, "5")]},
            {"plannedDurationInMinutes": 45, "transfers": 1, "status": "DISRUPTION",
             "legs": [leg("Utrecht Centraal", "Amsterdam Sloterdijk", 10, 40, "18"), leg("Amsterdam Sloterdijk", "Amsterdam Centraal", 45, 55, "2")]}]}
    if "disruptions" in url:
        return 200, [{"type": "MAINTENANCE", "title": "Utrecht Centraal - Amersfoort Centraal",
                      "timespans": [{"situation": {"label": "Geen treinen door werkzaamheden"}}]},
                     {"type": "DISRUPTION", "title": "Zwolle - Groningen", "timespans": []},
                     {"type": "DISRUPTION", "title": "Den Haag HS - Delft", "timespans": []},
                     {"type": "MAINTENANCE", "title": "Leiden Centraal - Alphen aan den Rijn", "timespans": []}]
    return 404, {"message": "not in the stub"}
