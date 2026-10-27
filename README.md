# Robot V.T

Telegram bot starter that receives Instagram links and creates Excel files from comment text the user is authorized to use.

## Render setup
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Add environment variable `BOT_TOKEN` using the secret from BotFather. Never commit the token to GitHub.
- After deployment, open `https://YOUR-SERVICE.onrender.com/setup-webhook` once to register the Telegram webhook.

Direct automatic collection from arbitrary Instagram posts is not included: it requires appropriate official/authorized access, and availability depends on Instagram permissions and the post.
