# Deploying on a DigitalOcean Droplet

Headless server: no display, no GUI login. You log in **locally**, then move
the session to the droplet. The droplet only ever runs `run` (headless).

Recommended droplet: Ubuntu 22.04/24.04, 1 GB RAM minimum (Chromium needs it).
DigitalOcean's default user is **root**, so paths below assume `/root`.

---

## 1. Log in locally (one time, needs a display)

On your laptop, where you can see a browser:

```bash
python3 main.py setup            # opens browser, log into TikTok, close window
```

This writes the session to `~/.tiktok-flamekeeper/profile/` and (if you used
the cookie route) `~/.tiktok-flamekeeper/cookies.json`.

## 2. Install on the droplet

```bash
ssh root@<droplet-ip>
git clone <your-repo> tiktok-flamekeeper && cd tiktok-flamekeeper
bash install.sh
```

`install.sh` installs Chromium + deps, copies files to `/opt/tiktok-flamekeeper`,
and sets up a systemd timer firing daily at **09:00 + up to 2h jitter**
(matches the 9–11 window in config).

## 3. Move your login to the droplet

**Option A — cookies (simplest, refreshable):**

```bash
# from your laptop
scp ~/.tiktok-flamekeeper/cookies.json root@<droplet-ip>:/root/
# on the droplet
cd /opt/tiktok-flamekeeper
python3 main.py import-cookies /root/cookies.json   # headless, no --show
```

**Option B — copy the whole profile:**

```bash
# from your laptop
rsync -av ~/.tiktok-flamekeeper/profile/ root@<droplet-ip>:/root/.tiktok-flamekeeper/profile/
```

Then put your edited config at `/root/.tiktok-flamekeeper/config.json`
(the 100-fact one). `scp` it over if needed.

## 4. Verify before trusting the timer

```bash
python3 main.py test            # headless; expect: "Login status: OK"
python3 main.py run             # sends one real DM; check the target
python3 main.py log --n 5       # confirm it logged
```

## 5. Timezone

Droplets default to **UTC**. The timer's `09:00` is therefore 09:00 UTC.
Set the droplet to your timezone so the streak DM lands at a sane local hour:

```bash
sudo timedatectl set-timezone Asia/Jakarta   # or your zone
sudo systemctl restart tiktok-flamekeeper.timer
```

## 6. Operating it

```bash
systemctl status tiktok-flamekeeper.timer     # next run time
journalctl -u tiktok-flamekeeper -f           # live logs
systemctl start tiktok-flamekeeper.service     # force a run now
```

---

## Caveats

- **Datacenter IP risk.** TikTok flags DigitalOcean IP ranges. You may hit a
  captcha / login challenge that the bot can't solve (sentinel will log
  `CAPTCHA detected`). If `test` shows `NOT LOGGED IN` right after a good cookie
  import, this is the likely cause. Mitigation: route through a residential
  proxy, or run from home instead.
- **Cookies expire.** When `test` starts failing, redo step 1 locally and
  re-import (step 3A). No re-install needed.
- **One account per profile.** The persistent profile holds one logged-in
  session; don't share it across accounts.
- **RAM.** Chromium can OOM on the 512 MB droplet. Use 1 GB+.
