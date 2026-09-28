"""Sample answers shaped like the Mollie API v2 (https://docs.mollie.com/reference), for recording a
cassette without a key. Record with IRIS_KEY_MOLLIE set (a test_ key) to replace them with real answers.
Payment tr_stub3 is paid; tr_stub4 has expired."""
import json

def answer(item, method, url, body):
    if url.endswith("/v2/methods"):
        return 200, {"count": 2, "_embedded": {"methods": [{"id": "ideal", "description": "iDEAL"},
                                                           {"id": "creditcard", "description": "Card"}]}}
    if url.endswith("/v2/payments") and method == "POST":
        b = json.loads(body)
        order = b["metadata"]["order"]
        pid = f"tr_stub{order}"
        return 201, {"resource": "payment", "id": pid, "status": "open", "amount": b["amount"],
                     "_links": {"checkout": {"href": f"https://www.mollie.com/checkout/select-method/{pid}"}}}
    if "/v2/payments/tr_stub3" in url:
        return 200, {"resource": "payment", "id": "tr_stub3", "status": "paid"}
    if "/v2/payments/tr_stub4" in url:
        return 200, {"resource": "payment", "id": "tr_stub4", "status": "expired"}
    return 404, {"status": 404, "title": "Not Found", "detail": "not in the stub"}
