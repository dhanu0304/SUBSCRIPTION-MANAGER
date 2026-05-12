# Subscription Manager

A Flask dashboard that lets users sign in with Gmail and scan read-only Gmail data for subscriptions, spam alerts, important mail, and transaction spending.

## Safe Setup

Never commit these files:

- `credentials.json`
- `token.json`
- `data/`
- `.env`

They are already blocked in `.gitignore`.

## Local Run

```bash
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## Vercel Environment Variables

Set these in Vercel Project Settings:

- `FLASK_SECRET_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`

Add this redirect URI to your Google OAuth client after Vercel creates your domain:

```text
https://your-vercel-domain.vercel.app/oauth2callback
```

For local development, add:

```text
http://127.0.0.1:5000/oauth2callback
http://localhost:5000/oauth2callback
```

## Important Production Note

This project stores scan results and OAuth tokens in local files for demo use. On Vercel, file storage is temporary. For a real production app, use a database and encrypted token storage.
