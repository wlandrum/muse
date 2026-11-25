# Phase 0 deployment: one artist, one VM

Runs today's Streamlit app for a single artist on a small Compute Engine VM in
the `root-logic-456318-q3` project, with HTTPS from Caddy and the artist's data
on the VM's disk (snapshotted daily). This is a stopgap until the multi-user
web app (see the plan) replaces it.

**Cost:** about $15–17/month (e2-small VM, static IP, 20 GB disk, snapshots).

## What this deployment does differently

| Setting | Value | Why |
|---|---|---|
| `MUSE_APP_PASSWORD` | set | Nothing renders, including the Google sign-in callback, until the password is entered. |
| `MUSE_SINGLE_USER=1` | | The Google token is kept on the VM's disk, so the artist doesn't reconnect every visit. |
| `MUSE_SEED_DEMO_DATA=0` | | No sample gigs, invoices, contacts, emails or voice samples. |
| Email sending | not available | The email agent only saves drafts to Gmail; the artist sends them from Gmail. |

## You need

- A domain, with access to its DNS. These steps use `app.<your-domain>`.
- `gcloud` signed in as an owner of `root-logic-456318-q3` (`gcloud auth login`), with billing enabled on the project.
- The artist's Anthropic API key, and a password to give them.

## 1. Create the VM

```bash
gcloud config set project root-logic-456318-q3
gcloud services enable compute.googleapis.com

gcloud compute addresses create muse-ip --region us-east1
gcloud compute addresses describe muse-ip --region us-east1 --format='value(address)'

gcloud compute instances create muse \
  --zone us-east1-b --machine-type e2-small \
  --image-family ubuntu-2404-lts-amd64 --image-project ubuntu-os-cloud \
  --boot-disk-size 20GB --address muse-ip --tags muse-web

gcloud compute firewall-rules create muse-web --allow tcp:80,tcp:443 --target-tags muse-web
```

Daily disk snapshots, kept 14 days:

```bash
gcloud compute resource-policies create snapshot-schedule muse-daily \
  --region us-east1 --daily-schedule --start-time 08:00 --max-retention-days 14
gcloud compute disks add-resource-policies muse --zone us-east1-b --resource-policies muse-daily
```

## 2. Point the domain at it

Add `A` records with the address printed above for `app` (the app), `@` (the
bare domain) and `www`. The bare domain serves the home page and privacy policy
in `deploy/site/`, which Google's consent screen requires before the app can be
published. Wait until `nslookup app.<your-domain>` returns the address before
step 5; Caddy needs that to get a certificate.

## 3. Google sign-in

In the Google Cloud console for `root-logic-456318-q3`:

1. **APIs & Services → Credentials →** the *Web application* OAuth client: add
   `https://app.<your-domain>` as an authorized redirect URI. Download its JSON;
   it becomes `credentials.json` on the VM.
2. **OAuth consent screen:** on *Branding*, name the app, add `<your-domain>` as
   an authorized domain, and set the home page to `https://<your-domain>` and
   the privacy policy to `https://<your-domain>/privacy`. Then on *Audience*,
   set the publishing status to **In production**. In *Testing* status, Google
   expires refresh tokens after 7 days. The app stays unverified, so the artist
   sees a warning screen once when connecting; that is expected.
3. Make sure the Calendar and Gmail APIs are enabled.

## 4. Put the app and its secrets on the VM

```bash
gcloud compute ssh muse --zone us-east1-b

# on the VM
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo git clone https://github.com/wlandrum/muse.git /opt/muse
sudo mkdir -p /var/lib/muse && sudo chown 1000:1000 /var/lib/muse
exit
```

From your machine, copy the secrets (never commit them):

```bash
cp deploy/muse.env.example muse.env   # fill in the key, password, artist name
gcloud compute scp muse.env path/to/web-client.json muse:~ --zone us-east1-b
gcloud compute ssh muse --zone us-east1-b -- '
  sudo install -m 600 ~/muse.env /opt/muse/deploy/muse.env &&
  sudo install -m 600 -o 1000 -g 1000 ~/web-client.json /var/lib/muse/credentials.json &&
  printf "MUSE_DOMAIN=app.<your-domain>\nMUSE_SITE_DOMAIN=<your-domain>\n" | sudo tee /opt/muse/deploy/.env &&
  rm ~/muse.env ~/web-client.json'
```

## 5. Start it

```bash
gcloud compute ssh muse --zone us-east1-b -- 'cd /opt/muse/deploy && sudo docker compose up -d --build'
```

Open `https://app.<your-domain>`, enter the password, click **Connect Google**
and sign in with the artist's account. Then try: "What's on my schedule this
week?" and "Check my inbox".

## Day to day

| Task | Command (on the VM, in `/opt/muse/deploy`) |
|---|---|
| Deploy a new version | `sudo git -C /opt/muse pull && sudo docker compose up -d --build` |
| Logs | `sudo docker compose logs -f muse` |
| Restart | `sudo docker compose restart muse` |
| Back up now | `gcloud compute disks snapshot muse --zone us-east1-b` (from your machine) |
| Disconnect Google | Sidebar → Disconnect, or remove `/var/lib/muse/token.json` |

All of the artist's data is in `/var/lib/muse`: `muse.db` (invoices,
contacts, notes, post drafts), `chroma_db/` (voice samples), `invoices/`
(PDFs) and `token.json`. Calendar events and email stay in Google.
