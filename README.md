# SUBSCRIPTION-MANAGER

## Local development

1. Create a Google OAuth client in the Google Cloud Console.
2. Use a Web application OAuth credential.
3. Add a redirect URI: `http://localhost:5000/oauth2callback`
4. Save the downloaded `credentials.json` file next to `app.py`.
5. Install packages: `pip install -r requirements.txt`
6. Run locally: `python app.py`

## Vercel deployment

This app uses Google OAuth credentials, but `credentials.json` is intentionally ignored by `.gitignore` and is not deployed to Vercel.

Use environment variables instead:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `FLASK_SECRET_KEY`

### Vercel setup steps

1. Open your Vercel project settings.
2. Add `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` from your Google Cloud OAuth client.
3. Add `FLASK_SECRET_KEY` with a random secret string.
4. In the Google Cloud Console, add your Vercel app URL redirect URI:
   - `https://<your-vercel-domain>/oauth2callback`
5. Redeploy the Vercel project.

### Important note

Vercel uses serverless instances, so the local file storage used by this app is not persistent across all invocations. This means:

- OAuth tokens and scanned Gmail data may be lost between serverless cold starts.
- The app is better suited for local development or for deployment on a platform with persistent storage.

If you need a production-ready deployment, use a service with stable disk storage or add a database/external storage layer.

## Deployment on Vercel

This app uses Google OAuth and does not deploy `credentials.json` to Vercel because that file is intentionally gitignored.

To run on Vercel, configure these environment variables in your project settings:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `FLASK_SECRET_KEY` (recommended for session security)

If you want to keep `credentials.json` local for development, do not commit it to GitHub. For deployment, use the env vars above instead.

---
