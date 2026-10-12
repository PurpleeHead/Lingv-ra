import hashlib
import hmac
import json
import unittest
import time
from urllib.parse import urlencode
from app.security import TelegramAuthError, validate_telegram_init_data


def make_data(token, user_id=42, auth_date=None):
    auth_date = int(time.time()) if auth_date is None else auth_date
    data = {
        "auth_date": str(auth_date),
        "query_id": "test-query",
        "user": json.dumps(
            {"id": user_id, "first_name": "Test"}, separators=(",", ":")
        ),
    }
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


class SecurityTests(unittest.TestCase):
    def test_valid_data(self):
        result = validate_telegram_init_data(make_data("token"), "token")
        self.assertEqual(result["id"], 42)

    def test_invalid_signature_rejected(self):
        with self.assertRaises(TelegramAuthError):
            validate_telegram_init_data(make_data("token"), "wrong-token")

    def test_expired_data_rejected(self):
        with self.assertRaises(TelegramAuthError):
            validate_telegram_init_data(
                make_data("token", auth_date=100), "token", max_age_seconds=10, now=200
            )

    def test_future_date_rejected(self):
        with self.assertRaises(TelegramAuthError):
            validate_telegram_init_data(
                make_data("token", auth_date=500), "token", now=100
            )

    def test_duplicate_fields_rejected(self):
        with self.assertRaises(TelegramAuthError):
            validate_telegram_init_data(make_data("token") + "&auth_date=1", "token")

    def test_non_numeric_user_id_rejected(self):
        with self.assertRaises(TelegramAuthError):
            validate_telegram_init_data(
                self.make_custom_user("token", "not-an-id"), "token"
            )

    @staticmethod
    def make_custom_user(token, user_id):
        data = {"auth_date": str(int(time.time())), "user": json.dumps({"id": user_id})}
        check = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        return urlencode(data)


if __name__ == "__main__":
    unittest.main()
