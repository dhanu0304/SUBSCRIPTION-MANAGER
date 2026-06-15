import base64
import hashlib
import json
import os

from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, flash, redirect, render_template, request, session, url_for

from gmail_sync import (
    GmailSyncError,
    credentials_status,
    finish_google_sign_in,
    gmail_profile,
    google_authorization_url,
    load_bank_transactions,
    load_important_mail,
    load_spam_messages,
    load_gmail_subscriptions,
    merge_subscriptions,
    sync_needed,
    sync_spam_messages,
    sync_important_mail,
    sync_bank_transactions,
    sync_gmail_subscriptions,
)


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-before-deploy")
app.config["GMAIL_AUTO_SYNC_MINUTES"] = int(os.environ.get("GMAIL_AUTO_SYNC_MINUTES", "15"))
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("VERCEL"))
if not os.environ.get("VERCEL"):
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


subscriptions = [
    {
        "name": "Netflix",
        "logo": "N",
        "price": 649,
        "renewal": "May 12, 2026",
        "cycle": "Monthly",
        "category": "Entertainment",
        "status": "Active",
        "accent": "netflix",
    },
    {
        "name": "Spotify",
        "logo": "S",
        "price": 119,
        "renewal": "May 16, 2026",
        "cycle": "Monthly",
        "category": "Music",
        "status": "Active",
        "accent": "spotify",
    },
    {
        "name": "Prime Video",
        "logo": "P",
        "price": 299,
        "renewal": "May 21, 2026",
        "cycle": "Monthly",
        "category": "Entertainment",
        "status": "Active",
        "accent": "prime",
    },
    {
        "name": "YouTube Premium",
        "logo": "Y",
        "price": 149,
        "renewal": "May 25, 2026",
        "cycle": "Monthly",
        "category": "Video",
        "status": "Active",
        "accent": "youtube",
    },
    {
        "name": "ChatGPT Plus",
        "logo": "C",
        "price": 1999,
        "renewal": "June 02, 2026",
        "cycle": "Monthly",
        "category": "Productivity",
        "status": "Active",
        "accent": "chatgpt",
    },
]

payments = [
    {"service": "Netflix", "date": "May 02, 2026", "amount": "Rs. 649", "status": "Paid"},
    {"service": "Spotify", "date": "May 01, 2026", "amount": "Rs. 119", "status": "Paid"},
    {"service": "ChatGPT Plus", "date": "Apr 30, 2026", "amount": "Rs. 1,999", "status": "Paid"},
    {"service": "Prime Video", "date": "Apr 28, 2026", "amount": "Rs. 299", "status": "Paid"},
]


def rupees(amount):
    return f"Rs. {amount:,.0f}"


def current_user_id():
    return session.get("user", {}).get("id")


def is_signed_in():
    return bool(current_user_id())


def credential_cipher():
    secret = app.config["SECRET_KEY"].encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def session_google_credentials():
    encrypted = session.get("google_credentials")
    if not encrypted:
        return None
    try:
        decrypted = credential_cipher().decrypt(encrypted.encode("utf-8"))
        return json.loads(decrypted.decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError):
        session.pop("google_credentials", None)
        return None


def save_session_google_credentials(credentials_data):
    serialized = json.dumps(credentials_data, separators=(",", ":")).encode("utf-8")
    session["google_credentials"] = credential_cipher().encrypt(serialized).decode("utf-8")


def current_gmail_status():
    status = credentials_status(current_user_id())
    status["token"] = status["token"] or bool(session_google_credentials())
    return status


def payment_rows(items):
    if not current_gmail_status()["data"]:
        return payments
    return [
        {
            "service": item["name"],
            "date": item["renewal"],
            "amount": rupees(item["price"]),
            "status": item["status"],
        }
        for item in items
    ]


def analytics_summary(items):
    total = sum(item["price"] for item in items)
    categories = {}
    for item in items:
        categories[item["category"]] = categories.get(item["category"], 0) + item["price"]

    highest_category = "No data"
    highest_percent = 0
    if categories and total:
        highest_category = max(categories, key=categories.get)
        highest_percent = round((categories[highest_category] / total) * 100)

    return {
        "monthly_total": total,
        "monthly_total_label": rupees(total),
        "active_count": len(items),
        "yearly_total_label": rupees(total * 12),
        "highest_category": highest_category,
        "highest_percent": highest_percent,
    }


def chart_data(items):
    total = sum(item["price"] for item in items)
    categories = {}
    for item in items:
        categories[item["category"]] = categories.get(item["category"], 0) + item["price"]

    return {
        "service_labels": [item["name"] for item in items],
        "service_values": [item["price"] for item in items],
        "category_labels": list(categories.keys()),
        "category_values": list(categories.values()),
        "trend_labels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
        "trend_values": [total, total, total, total, total, total],
    }


def bank_chart_data(bank_data):
    monthly = list(reversed(bank_data["monthly"]))
    return {
        "bank_month_labels": [item["month"] for item in monthly],
        "bank_month_values": [item["total"] for item in monthly],
    }


def summary():
    items = load_gmail_subscriptions(subscriptions, current_user_id())
    next_item = items[0] if items else {"name": "No renewals", "renewal": "Sync Gmail"}
    total = sum(item["price"] for item in items)
    return {
        "monthly_total": rupees(total),
        "active_count": len(items),
        "next_name": next_item["name"],
        "next_renewal": next_item["renewal"],
    }


def auto_sync_gmail(data_type, user_id):
    if not sync_needed(user_id, data_type, app.config["GMAIL_AUTO_SYNC_MINUTES"]):
        return

    credentials_data = session_google_credentials()
    try:
        if data_type == "subscriptions":
            imported = sync_gmail_subscriptions(user_id, credentials_data)
            merge_subscriptions(subscriptions, imported, user_id)
        elif data_type == "spam":
            sync_spam_messages(user_id, credentials_data)
        elif data_type == "important":
            sync_important_mail(user_id, credentials_data)
        elif data_type == "bank":
            sync_bank_transactions(user_id, credentials_data)
        if credentials_data:
            save_session_google_credentials(credentials_data)
    except GmailSyncError as error:
        flash(f"Automatic Gmail refresh failed: {error}", "error")


@app.context_processor
def inject_user_profile():
    user_id = current_user_id()
    return {
        "user_profile": gmail_profile(user_id),
        "signed_in": is_signed_in(),
    }


@app.before_request
def require_login():
    public_endpoints = {"login", "google_login", "oauth2callback", "static"}
    if request.endpoint in public_endpoints or request.endpoint is None:
        return None
    if not is_signed_in():
        return redirect(url_for("login"))
    return None


@app.route("/login")
def login():
    return render_template(
        "login.html",
        title="Sign In",
        active_page="login",
        gmail_status=current_gmail_status(),
    )


@app.route("/login/google")
def google_login():
    try:
        redirect_uri = url_for("oauth2callback", _external=True)
        authorization_url, state = google_authorization_url(redirect_uri)
        session["oauth_state"] = state
        return redirect(authorization_url)
    except GmailSyncError as error:
        flash(str(error), "error")
        return redirect(url_for("login"))


@app.route("/oauth2callback")
def oauth2callback():
    if request.args.get("state") != session.get("oauth_state"):
        flash("Google sign-in state did not match. Please try again.", "error")
        return redirect(url_for("login"))
    try:
        redirect_uri = url_for("oauth2callback", _external=True)
        user = finish_google_sign_in(request.url, redirect_uri)
        save_session_google_credentials(user.pop("credentials"))
        session["user"] = user
        session.pop("oauth_state", None)
        flash(f"Signed in as {user['email']}.", "success")
        return redirect(url_for("dashboard"))
    except GmailSyncError as error:
        flash(str(error), "error")
        return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Signed out successfully.", "success")
    return redirect(url_for("login"))


@app.route("/")
def dashboard():
    user_id = current_user_id()
    auto_sync_gmail("subscriptions", user_id)
    items = load_gmail_subscriptions(subscriptions, user_id)
    spam_messages = load_spam_messages(user_id)
    important_mail = load_important_mail(user_id)
    bank_data = load_bank_transactions(user_id)
    useful_spam = [message for message in spam_messages if message["recommendation"] == "Review"]
    attention_count = len(important_mail["security"]) + len(important_mail["attention"])
    return render_template(
        "dashboard.html",
        title="Dashboard",
        active_page="dashboard",
        subscriptions=items,
        payments=payment_rows(items),
        summary=summary(),
        gmail_status=current_gmail_status(),
        useful_spam=useful_spam,
        important_mail=important_mail,
        attention_count=attention_count,
        chart_data=chart_data(items),
        bank_data=bank_data,
    )


@app.route("/subscriptions")
def subscription_management():
    user_id = current_user_id()
    auto_sync_gmail("subscriptions", user_id)
    return render_template(
        "subscriptions.html",
        title="Subscriptions",
        active_page="subscriptions",
        subscriptions=load_gmail_subscriptions(subscriptions, user_id),
        gmail_status=current_gmail_status(),
    )


@app.post("/sync-gmail")
def sync_gmail():
    user_id = current_user_id()
    credentials_data = session_google_credentials()
    try:
        imported = sync_gmail_subscriptions(user_id, credentials_data)
        merge_subscriptions(subscriptions, imported, user_id)
        if credentials_data:
            save_session_google_credentials(credentials_data)
        flash(f"Gmail sync complete. Found {len(imported)} subscription payment email(s).", "success")
    except GmailSyncError as error:
        flash(str(error), "error")
    return redirect(request.referrer or url_for("dashboard"))


@app.post("/sync-spam")
def sync_spam():
    user_id = current_user_id()
    credentials_data = session_google_credentials()
    try:
        messages = sync_spam_messages(user_id, credentials_data)
        if credentials_data:
            save_session_google_credentials(credentials_data)
        useful_count = len([message for message in messages if message["recommendation"] == "Review"])
        flash(f"Spam scan complete. Found {len(messages)} spam email(s), {useful_count} worth reviewing.", "success")
    except GmailSyncError as error:
        flash(str(error), "error")
    return redirect(request.referrer or url_for("spam_monitor"))


@app.post("/sync-important")
def sync_important():
    user_id = current_user_id()
    credentials_data = session_google_credentials()
    try:
        data = sync_important_mail(user_id, credentials_data)
        if credentials_data:
            save_session_google_credentials(credentials_data)
        total = len(data["security"]) + len(data["attention"])
        flash(f"Important mail scan complete. Found {total} email(s) worth noticing.", "success")
    except GmailSyncError as error:
        flash(str(error), "error")
    return redirect(request.referrer or url_for("important_mail"))


@app.post("/sync-bank")
def sync_bank():
    user_id = current_user_id()
    credentials_data = session_google_credentials()
    try:
        data = sync_bank_transactions(user_id, credentials_data)
        if credentials_data:
            save_session_google_credentials(credentials_data)
        flash(f"Bank transaction scan complete. Found {len(data['transactions'])} spending email(s).", "success")
    except GmailSyncError as error:
        flash(str(error), "error")
    return redirect(request.referrer or url_for("bank_transactions"))


@app.route("/gmail-setup")
def gmail_setup():
    user_id = current_user_id()
    return render_template(
        "gmail_setup.html",
        title="Gmail Setup",
        active_page="gmail",
        gmail_status=current_gmail_status(),
    )


@app.route("/spam")
def spam_monitor():
    user_id = current_user_id()
    auto_sync_gmail("spam", user_id)
    messages = load_spam_messages(user_id)
    useful_count = len([message for message in messages if message["recommendation"] == "Review"])
    return render_template(
        "spam_monitor.html",
        title="Spam Monitor",
        active_page="spam",
        messages=messages,
        useful_count=useful_count,
        gmail_status=current_gmail_status(),
    )


@app.route("/important")
def important_mail():
    user_id = current_user_id()
    auto_sync_gmail("important", user_id)
    data = load_important_mail(user_id)
    total = len(data["security"]) + len(data["attention"])
    return render_template(
        "important_mail.html",
        title="Important Mail",
        active_page="important",
        mail=data,
        total=total,
        gmail_status=current_gmail_status(),
    )


@app.route("/bank")
def bank_transactions():
    user_id = current_user_id()
    auto_sync_gmail("bank", user_id)
    data = load_bank_transactions(user_id)
    current_month = data["monthly"][0] if data["monthly"] else {"month": "No data", "total": 0, "total_label": "Rs. 0"}
    return render_template(
        "bank_transactions.html",
        title="Bank Transactions",
        active_page="bank",
        bank=data,
        current_month=current_month,
        chart_data=bank_chart_data(data),
        gmail_status=current_gmail_status(),
    )


@app.route("/add")
def add_subscription():
    return render_template("add_subscription.html", title="Add Subscription", active_page="add")


@app.route("/analytics")
def analytics():
    items = load_gmail_subscriptions(subscriptions, current_user_id())
    return render_template(
        "analytics.html",
        title="Analytics",
        active_page="analytics",
        analytics=analytics_summary(items),
        chart_data=chart_data(items),
    )


@app.route("/settings")
def settings():
    return render_template("settings.html", title="Profile Settings", active_page="settings")


if __name__ == "__main__":
    app.run(debug=True)
