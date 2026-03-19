import base64

from app.services.gmail_parser import decode_gmail_body, normalize_gmail_message


def _b64(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("utf-8").rstrip("=")


def test_decode_body():
    assert decode_gmail_body(_b64("hello world")) == "hello world"


def test_normalize_message_extracts_headers_and_flags():
    message = {
        "id": "msg-1",
        "threadId": "thread-1",
        "snippet": "Limited time offer",
        "labelIds": ["INBOX", "PROMOTIONS", "UNREAD"],
        "internalDate": "1710000000000",
        "payload": {
            "headers": [
                {"name": "From", "value": "Promo Team <offers@example.com>"},
                {"name": "Subject", "value": "Weekend sale"},
                {"name": "List-Unsubscribe", "value": "<mailto:unsubscribe@example.com>"},
            ],
            "body": {"data": _b64("Discount inside")},
        },
    }

    normalized = normalize_gmail_message(message)

    assert normalized.gmail_message_id == "msg-1"
    assert normalized.sender_email == "offers@example.com"
    assert normalized.sender_domain == "example.com"
    assert normalized.subject == "Weekend sale"
    assert normalized.has_unsubscribe is True
    assert normalized.is_read is False
