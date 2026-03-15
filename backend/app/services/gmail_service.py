from typing import List, Dict


class GmailService:
    def fetch_recent_emails(self) -> List[Dict]:
        """
        Placeholder for Gmail API integration.
        Later this will:
        - use OAuth credentials
        - call Gmail API
        - fetch recent emails
        - normalize payload
        """
        return [
            {
                "gmail_message_id": "sample-msg-1",
                "gmail_thread_id": "sample-thread-1",
                "sender_name": "Promo Team",
                "sender_email": "offers@example.com",
                "sender_domain": "example.com",
                "subject": "Weekend sale is live",
                "snippet": "Limited-time discount for members.",
                "body_text": "Limited-time discount for members. Unsubscribe anytime.",
                "gmail_labels": "INBOX,PROMOTIONS",
                "has_unsubscribe": True,
            }
        ]