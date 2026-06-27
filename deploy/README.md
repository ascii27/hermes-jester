# Deploying hermes-jester on exe.dev

Target VM: **`lectern-queenside.exe.xyz`** → service at `https://lectern-queenside.exe.xyz`.

## 1. Google OAuth client (for the UI)

In the [Google Cloud Console](https://console.cloud.google.com/apis/credentials):

1. Create an **OAuth 2.0 Client ID** of type *Web application*.
2. Authorized redirect URI: `https://lectern-queenside.exe.xyz/auth/callback`
3. Copy the **Client ID** and **Client secret** into `.env`.

## 2. Get the code onto the VM

```bash
ssh lectern-queenside.exe.xyz                      # shell on the VM
git clone <this-repo> hermes-jester && cd hermes-jester
python3 -m venv .venv
.venv/bin/pip install -e .
cp deploy/env.example .env && $EDITOR .env         # fill in secrets
```

Generate the session secret:

```bash
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 3. Initialise the database and mint keys

```bash
set -a; source .env; set +a
.venv/bin/python -m jester.admin init-db
.venv/bin/python -m jester.admin create-key --name hermes-cron --scope read    # for hermes
.venv/bin/python -m jester.admin create-key --name acme-webhook --scope write  # per sender
```

Each `create-key` prints the token **once** — store it securely. (You can also mint
keys later from the UI under *Keys*.)

## 4. Run the service

```bash
sudo cp deploy/jester.service /etc/systemd/system/jester.service
# edit User / paths in the unit if your VM differs
sudo systemctl enable --now jester
systemctl status jester
```

The service listens on port 8077; exe.dev's proxy forwards `https://lectern-queenside.exe.xyz/` to it.

## 5. Make the proxy public

External apps authenticate with **our** bearer tokens, so the exe.dev login gate
must be off:

```bash
ssh exe.dev share set-public lectern-queenside
```

> Note: making the proxy public disables exe.dev's built-in identity headers. The
> UI's Google sign-in is handled entirely inside the app (steps 1 & 3), so this is
> expected — the app owns all authentication.

## 6. Verify

```bash
curl https://lectern-queenside.exe.xyz/health        # {"status":"ok"}
# open https://lectern-queenside.exe.xyz/  -> redirects to Google sign-in
```

See the repo `README.md` for the API reference and the hermes cron loop.
