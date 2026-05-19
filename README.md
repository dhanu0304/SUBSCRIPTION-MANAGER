# SUBSCRIPTION-MANAGER

## Deployment on Vercel

This app uses Google OAuth and does not deploy `credentials.json` to Vercel because that file is intentionally gitignored.

To run on Vercel, configure these environment variables in your project settings:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `FLASK_SECRET_KEY` (recommended for session security)

If you want to keep `credentials.json` local for development, do not commit it to GitHub. For deployment, use the env vars above instead.

---
