import base64
import json
import os
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(
    os.environ.get(
        "APP_DATA_DIR",
        "/tmp/subscription-manager-data" if os.environ.get("VERCEL") else str(BASE_DIR / "data"),
    )
)
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


SERVICE_PROFILES = {
    "netflix": {"name": "Netflix", "logo": "N", "category": "Entertainment", "accent": "netflix"},
    "spotify": {"name": "Spotify", "logo": "S", "category": "Music", "accent": "spotify"},
    "prime": {"name": "Prime Video", "logo": "P", "category": "Entertainment", "accent": "prime"},
    "amazon prime": {"name": "Prime Video", "logo": "P", "category": "Entertainment", "accent": "prime"},
    "youtube": {"name": "YouTube Premium", "logo": "Y", "category": "Video", "accent": "youtube"},
    "google play": {"name": "YouTube Premium", "logo": "Y", "category": "Video", "accent": "youtube"},
    "chatgpt": {"name": "ChatGPT Plus", "logo": "C", "category": "Productivity", "accent": "chatgpt"},
    "openai": {"name": "ChatGPT Plus", "logo": "C", "category": "Productivity", "accent": "chatgpt"},
}


class GmailSyncError(Exception):
    pass


def credentials_status(user_id=None):
    return {
        "credentials": _has_google_credentials(),
        "token": _token_file(user_id).exists() if user_id else False,
        "data": _gmail_data_file(user_id).exists() if user_id else False,
        "profile": _gmail_profile_file(user_id).exists() if user_id else False,
        "spam": _spam_data_file(user_id).exists() if user_id else False,
        "important": _important_mail_file(user_id).exists() if user_id else False,
        "bank": _bank_transactions_file(user_id).exists() if user_id else False,
    }


def google_authorization_url(redirect_uri):
    if not _has_google_credentials():
        raise GmailSyncError("Missing Google OAuth credentials. Add credentials.json locally or set Vercel env vars.")
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as error:
        raise GmailSyncError("Gmail packages are not installed. Run: pip install -r requirements.txt") from error

    flow = _oauth_flow(Flow, redirect_uri)
    return flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="select_account consent",
    )


def finish_google_sign_in(authorization_response, redirect_uri):
    if not _has_google_credentials():
        raise GmailSyncError("Missing Google OAuth credentials. Add credentials.json locally or set Vercel env vars.")
    try:
        from google_auth_oauthlib.flow import Flow
        from googleapiclient.discovery import build
    except ImportError as error:
        raise GmailSyncError("Gmail packages are not installed. Run: pip install -r requirements.txt") from error

    flow = _oauth_flow(Flow, redirect_uri)
    flow.fetch_token(authorization_response=authorization_response)
    creds = flow.credentials
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    email = profile.get("emailAddress", "gmail-user")
    user_id = _safe_user_id(email)
    _user_dir(user_id).mkdir(parents=True, exist_ok=True)
    _token_file(user_id).write_text(creds.to_json(), encoding="utf-8")
    _save_gmail_profile(service, user_id)
    _migrate_legacy_data(user_id)
    return {"id": user_id, "email": email, "initials": _initials(email)}


def load_gmail_subscriptions(fallback, user_id=None):
    data_file = _gmail_data_file(user_id)
    if not user_id or not data_file.exists():
        return fallback
    with data_file.open("r", encoding="utf-8") as file:
        return json.load(file)


def gmail_profile(user_id=None):
    profile_file = _gmail_profile_file(user_id)
    if not user_id or not profile_file.exists():
        return {"email": "Not connected", "initials": "GM"}
    with profile_file.open("r", encoding="utf-8") as file:
        profile = json.load(file)
    email = profile.get("email", "Gmail")
    return {"email": email, "initials": _initials(email)}


def merge_subscriptions(fallback, imported, user_id):
    _user_dir(user_id).mkdir(parents=True, exist_ok=True)
    ignored = _ignored_services(user_id)
    merged = sorted(
        [item for item in imported if item["name"] not in ignored],
        key=lambda item: item.get("days_left", 999),
    )
    with _gmail_data_file(user_id).open("w", encoding="utf-8") as file:
        json.dump(merged, file, indent=2)
    return merged


def sync_gmail_subscriptions(user_id):
    service = _gmail_service(user_id)
    _save_gmail_profile(service, user_id)
    query = (
        'newer_than:180d (receipt OR invoice OR payment OR subscription OR renewal) '
        '(Netflix OR Spotify OR "Prime Video" OR YouTube OR OpenAI OR ChatGPT)'
    )
    response = service.users().messages().list(userId="me", q=query, maxResults=30).execute()
    messages = response.get("messages", [])
    imported = {}

    for message in messages:
        detail = service.users().messages().get(userId="me", id=message["id"], format="full").execute()
        parsed = _parse_subscription_message(detail)
        if parsed:
            imported[parsed["name"]] = parsed

    return sorted(imported.values(), key=lambda item: item.get("days_left", 999))


def load_spam_messages(user_id=None):
    data_file = _spam_data_file(user_id)
    if not user_id or not data_file.exists():
        return []
    with data_file.open("r", encoding="utf-8") as file:
        return json.load(file)


def sync_spam_messages(user_id):
    service = _gmail_service(user_id)
    _save_gmail_profile(service, user_id)
    response = service.users().messages().list(userId="me", q="in:spam newer_than:30d", maxResults=25).execute()
    messages = response.get("messages", [])
    parsed_messages = []

    for message in messages:
        detail = service.users().messages().get(userId="me", id=message["id"], format="metadata").execute()
        parsed_messages.append(_parse_spam_message(detail))

    _user_dir(user_id).mkdir(parents=True, exist_ok=True)
    with _spam_data_file(user_id).open("w", encoding="utf-8") as file:
        json.dump(parsed_messages, file, indent=2)
    return parsed_messages


def load_important_mail(user_id=None):
    data_file = _important_mail_file(user_id)
    if not user_id or not data_file.exists():
        return {"security": [], "attention": []}
    with data_file.open("r", encoding="utf-8") as file:
        return json.load(file)


def sync_important_mail(user_id):
    service = _gmail_service(user_id)
    _save_gmail_profile(service, user_id)
    query = (
        'newer_than:365d -in:spam '
        '(password OR passcode OR "security alert" OR login OR verification OR otp OR '
        'invoice OR receipt OR payment OR refund OR deadline OR exam OR admission OR '
        'interview OR application OR bank OR account)'
    )
    response = service.users().messages().list(userId="me", q=query, maxResults=80).execute()
    messages = response.get("messages", [])
    security = []
    attention = []
    seen_subjects = set()

    for message in messages:
        detail = service.users().messages().get(userId="me", id=message["id"], format="metadata").execute()
        parsed = _parse_important_message(detail)
        key = (parsed["sender"], parsed["subject"])
        if key in seen_subjects:
            continue
        seen_subjects.add(key)
        if parsed["bucket"] == "security":
            security.append(parsed)
        else:
            attention.append(parsed)

    data = {"security": security[:25], "attention": attention[:35]}
    _user_dir(user_id).mkdir(parents=True, exist_ok=True)
    with _important_mail_file(user_id).open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
    return data


def load_bank_transactions(user_id=None):
    data_file = _bank_transactions_file(user_id)
    if not user_id or not data_file.exists():
        return {"monthly": [], "transactions": []}
    with data_file.open("r", encoding="utf-8") as file:
        return json.load(file)


def sync_bank_transactions(user_id):
    service = _gmail_service(user_id)
    _save_gmail_profile(service, user_id)
    query = (
        'newer_than:365d -in:spam '
        '(fampay OR "FamPay" OR "FamApp" OR UPI OR debit OR debited OR spent OR paid OR payment OR transaction OR bank OR card)'
    )
    response = service.users().messages().list(userId="me", q=query, maxResults=120).execute()
    messages = response.get("messages", [])
    transactions = []
    seen = set()

    for message in messages:
        detail = service.users().messages().get(userId="me", id=message["id"], format="full").execute()
        parsed = _parse_bank_transaction(detail)
        if not parsed:
            continue
        key = (parsed["date"], parsed["amount"], parsed["subject"])
        if key in seen:
            continue
        seen.add(key)
        transactions.append(parsed)

    transactions = sorted(transactions, key=lambda item: item["sort_date"], reverse=True)
    data = {"monthly": _monthly_totals(transactions), "transactions": transactions[:80]}
    _user_dir(user_id).mkdir(parents=True, exist_ok=True)
    with _bank_transactions_file(user_id).open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
    return data


def _gmail_service(user_id):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as error:
        raise GmailSyncError("Gmail packages are not installed. Run: pip install -r requirements.txt") from error

    token_file = _token_file(user_id)
    if not user_id or not token_file.exists():
        raise GmailSyncError("Please sign in with Google first.")

    creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_file.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise GmailSyncError("Your Google session expired. Please sign in again.")
    return build("gmail", "v1", credentials=creds)


def _save_gmail_profile(service, user_id):
    profile = service.users().getProfile(userId="me").execute()
    _user_dir(user_id).mkdir(parents=True, exist_ok=True)
    with _gmail_profile_file(user_id).open("w", encoding="utf-8") as file:
        json.dump({"email": profile.get("emailAddress", "Gmail")}, file, indent=2)


def _parse_subscription_message(message):
    headers = _headers(message)
    text = " ".join([headers.get("from", ""), headers.get("subject", ""), message.get("snippet", ""), _extract_body(message.get("payload", {}))])
    service = _detect_service(text)
    price = _detect_price(text)
    paid_at = _detect_date(headers.get("date"))
    if not service or not price:
        return None

    renewal_date = _next_monthly_renewal(paid_at)
    days_left = max((renewal_date.date() - datetime.now().date()).days, 0)
    return {
        **service,
        "price": price,
        "renewal": renewal_date.strftime("%b %d, %Y"),
        "cycle": "Monthly",
        "status": "Active" if days_left > 0 else "Due",
        "days_left": days_left,
        "source": "Gmail",
    }


def _parse_spam_message(message):
    headers = _headers(message)
    sender = headers.get("from", "Unknown sender")
    subject = headers.get("subject", "No subject")
    snippet = message.get("snippet", "")
    recommendation, reason = _spam_recommendation(f"{sender} {subject} {snippet}")
    return {
        "sender": sender,
        "subject": subject,
        "snippet": snippet,
        "date": _detect_date(headers.get("date")).strftime("%b %d, %Y"),
        "recommendation": recommendation,
        "reason": reason,
    }


def _parse_important_message(message):
    headers = _headers(message)
    sender = headers.get("from", "Unknown sender")
    subject = headers.get("subject", "No subject")
    snippet = _redact_sensitive_snippet(message.get("snippet", ""))
    bucket, priority, reason = _important_recommendation(f"{sender} {subject} {snippet}")
    return {
        "sender": sender,
        "subject": subject,
        "snippet": snippet,
        "date": _detect_date(headers.get("date")).strftime("%b %d, %Y"),
        "bucket": bucket,
        "priority": priority,
        "reason": reason,
    }


def _parse_bank_transaction(message):
    headers = _headers(message)
    sender = headers.get("from", "Unknown sender")
    subject = headers.get("subject", "No subject")
    snippet = message.get("snippet", "")
    text = f"{sender} {subject} {snippet} {_extract_body(message.get('payload', {}))}"
    lowered = text.lower()
    if not _looks_like_spend(lowered):
        return None

    amount = _detect_price(text)
    if not amount:
        return None

    paid_at = _detect_date(headers.get("date"))
    return {
        "sender": sender,
        "subject": subject,
        "snippet": _redact_sensitive_snippet(snippet),
        "date": paid_at.strftime("%b %d, %Y"),
        "month": paid_at.strftime("%b %Y"),
        "sort_date": paid_at.strftime("%Y-%m-%d"),
        "amount": amount,
        "amount_label": f"Rs. {amount:,.0f}",
        "merchant": _detect_merchant(text, subject),
        "source": _detect_payment_source(text),
        "type": "Spent",
    }


def _headers(message):
    return {
        header["name"].lower(): header["value"]
        for header in message.get("payload", {}).get("headers", [])
    }


def _looks_like_spend(lowered):
    spend_words = ["debited", "spent", "paid", "payment", "sent", "purchase", "transaction"]
    incoming_words = ["credited", "received", "refund received", "cashback", "reward"]
    return any(word in lowered for word in spend_words) and not any(word in lowered for word in incoming_words)


def _detect_merchant(text, subject):
    patterns = [
        r"(?:to|at|for|merchant)\s+([A-Z][A-Za-z0-9& ._-]{2,40})",
        r"paid\s+to\s+([A-Za-z0-9& ._-]{2,40})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            merchant = match.group(1).strip(" .-_")
            if len(merchant) <= 45:
                return merchant
    return subject[:48]


def _detect_payment_source(text):
    lowered = text.lower()
    if "fampay" in lowered or "fam pay" in lowered or " fam " in lowered:
        return "FamPay"
    if "upi" in lowered:
        return "UPI"
    if "card" in lowered:
        return "Card"
    if "bank" in lowered:
        return "Bank"
    return "Gmail"


def _monthly_totals(transactions):
    totals = {}
    for transaction in transactions:
        month = transaction["month"]
        totals[month] = totals.get(month, 0) + transaction["amount"]
    return [{"month": month, "total": total, "total_label": f"Rs. {total:,.0f}"} for month, total in totals.items()]


def _important_recommendation(text):
    lowered = text.lower()
    security_keywords = {
        "password": "Password or account access related",
        "passcode": "Passcode or account access related",
        "otp": "OTP or verification code related",
        "verification": "Verification email",
        "security alert": "Security alert",
        "login": "Login or account activity alert",
        "two-step": "Two-step verification related",
        "2-step": "Two-step verification related",
        "account": "Account access related",
    }
    attention_keywords = {
        "invoice": "Invoice or bill",
        "receipt": "Payment receipt",
        "payment": "Payment related",
        "refund": "Refund related",
        "bank": "Banking or finance related",
        "deadline": "Deadline or due date",
        "exam": "Academic email",
        "admission": "Admission or college related",
        "interview": "Interview related",
        "application": "Application update",
        "subscription": "Subscription related",
        "renewal": "Renewal related",
        "delivery": "Delivery or order update",
        "order": "Order update",
    }
    for keyword, reason in security_keywords.items():
        if keyword in lowered:
            return "security", "High", reason
    for keyword, reason in attention_keywords.items():
        if keyword in lowered:
            return "attention", "Medium", reason
    return "attention", "Low", "Looks potentially useful"


def _spam_recommendation(text):
    lowered = text.lower()
    useful_keywords = {
        "otp": "May contain an OTP or verification code",
        "verification": "May be a verification email",
        "invoice": "May contain a bill or invoice",
        "receipt": "May contain a payment receipt",
        "payment": "May relate to a payment",
        "subscription": "May relate to a subscription",
        "renewal": "May relate to a renewal",
        "security alert": "May be an account security alert",
        "login": "May be a login alert",
        "password": "May relate to account access",
        "refund": "May relate to a refund",
        "order": "May relate to an order",
        "delivery": "May relate to a delivery",
        "exam": "May relate to academics",
        "admission": "May relate to academics",
    }
    ignore_keywords = ["lottery", "winner", "casino", "claim prize", "crypto", "loan approved"]
    for keyword, reason in useful_keywords.items():
        if keyword in lowered:
            return "Review", reason
    for keyword in ignore_keywords:
        if keyword in lowered:
            return "Ignore", "Looks like promotional or scam spam"
    return "Ignore", "No important payment, account, or academic signal found"


def _detect_service(text):
    lowered = text.lower()
    for keyword, profile in SERVICE_PROFILES.items():
        if keyword in lowered:
            return profile.copy()
    return None


def _detect_price(text):
    patterns = [
        r"(?:₹|rs\.?|inr|rupees?)\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        r"([0-9,]+(?:\.[0-9]{1,2})?)\s*(?:₹|rs\.?|inr|rupees?)",
    ]
    values = []
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            try:
                values.append(float(match.replace(",", "")))
            except ValueError:
                continue
    return int(max(values)) if values else None


def _detect_date(raw_date):
    if not raw_date:
        return datetime.now()
    try:
        parsed = parsedate_to_datetime(raw_date)
        if parsed is None:
            return datetime.now()
        return parsed.replace(tzinfo=None)
    except (AttributeError, TypeError, ValueError):
        return datetime.now()


def _next_monthly_renewal(paid_at):
    renewal_date = paid_at + timedelta(days=30)
    now = datetime.now()
    while renewal_date.date() < now.date():
        renewal_date += timedelta(days=30)
    return renewal_date


def _extract_body(payload):
    chunks = []
    data = payload.get("body", {}).get("data")
    if data:
        chunks.append(_decode(data))
    for part in payload.get("parts", []) or []:
        chunks.append(_extract_body(part))
    return " ".join(chunks)


def _decode(data):
    try:
        return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore")
    except (ValueError, UnicodeDecodeError):
        return ""


def _redact_sensitive_snippet(snippet):
    snippet = re.sub(r"\b\d{4,8}\b", "[code hidden]", snippet)
    snippet = re.sub(r"(?i)(password|otp|passcode)(\s*[:=-]\s*)\S+", r"\1\2[hidden]", snippet)
    return snippet


def _initials(email):
    name = email.split("@", 1)[0]
    parts = [part for part in re.split(r"[^a-zA-Z0-9]+", name) if part]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return name[:2].upper() if name else "GM"


def _user_dir(user_id):
    return DATA_DIR / "users" / _safe_user_id(user_id or "guest")


def _token_file(user_id):
    return _user_dir(user_id) / "token.json"


def _gmail_data_file(user_id):
    return _user_dir(user_id) / "gmail_subscriptions.json"


def _gmail_profile_file(user_id):
    return _user_dir(user_id) / "gmail_profile.json"


def _spam_data_file(user_id):
    return _user_dir(user_id) / "spam_messages.json"


def _important_mail_file(user_id):
    return _user_dir(user_id) / "important_mail.json"


def _bank_transactions_file(user_id):
    return _user_dir(user_id) / "bank_transactions.json"


def _ignored_services_file(user_id):
    return _user_dir(user_id) / "ignored_services.json"


def _ignored_services(user_id):
    ignored_file = _ignored_services_file(user_id)
    if not ignored_file.exists():
        return set()
    with ignored_file.open("r", encoding="utf-8") as file:
        return set(json.load(file))


def _safe_user_id(value):
    return re.sub(r"[^a-zA-Z0-9_.@-]", "_", value or "user")


def _has_google_credentials():
    return CREDENTIALS_FILE.exists() or bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))


def _oauth_flow(flow_class, redirect_uri):
    if CREDENTIALS_FILE.exists():
        return flow_class.from_client_secrets_file(str(CREDENTIALS_FILE), scopes=SCOPES, redirect_uri=redirect_uri)

    client_config = {
        "web": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    return flow_class.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)


def _migrate_legacy_data(user_id):
    legacy_files = {
        DATA_DIR / "gmail_subscriptions.json": _gmail_data_file(user_id),
        DATA_DIR / "gmail_profile.json": _gmail_profile_file(user_id),
        DATA_DIR / "spam_messages.json": _spam_data_file(user_id),
        DATA_DIR / "important_mail.json": _important_mail_file(user_id),
        DATA_DIR / "bank_transactions.json": _bank_transactions_file(user_id),
        DATA_DIR / "ignored_services.json": _ignored_services_file(user_id),
    }
    for source, target in legacy_files.items():
        if source.exists() and not target.exists():
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
