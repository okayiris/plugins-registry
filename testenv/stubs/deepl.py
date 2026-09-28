"""Sample answers shaped like the DeepL API v2 (https://developers.deepl.com/docs), for recording a
cassette without a key. Record with IRIS_KEY_DEEPL set to replace them with real answers.
The stub plays a Pro key: the free host says "Wrong endpoint", as DeepL does, so the switch is tested."""
import json

WORDS = {("Goedemorgen allemaal", "EN-GB"): "Good morning everyone",
         ("Good morning", "DE"): "Guten Morgen",
         ("How are you?", "NL"): "Hoe gaat het met u?",
         ("Hallo", "EN-GB"): "Hello"}
SOURCE = {"Goedemorgen allemaal": "NL", "Hallo": "NL", "Good morning": "EN", "How are you?": "EN"}


def answer(item, method, url, body):
    if "api-free.deepl.com" in url:
        return 403, {"message": "Wrong endpoint. Use https://api.deepl.com"}
    if url.endswith("/translate"):
        b = json.loads(body)
        text, target = b["text"][0], b["target_lang"]
        return 200, {"translations": [{"detected_source_language": SOURCE.get(text, "EN"),
                                       "text": WORDS.get((text, target), text)}]}
    if url.endswith("/usage"):
        return 200, {"character_count": 12345, "character_limit": 500000}
    if "languages" in url:
        return 200, [{"language": "DE", "name": "German"}, {"language": "EN-GB", "name": "English (British)"},
                     {"language": "NL", "name": "Dutch"}]
    return 404, {"message": "not in the stub"}
