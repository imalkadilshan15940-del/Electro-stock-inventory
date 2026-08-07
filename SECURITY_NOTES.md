# Security notes

## License key verification — now public/private key signing

License keys are verified using a **public/private keypair** (ECDSA,
P-256 curve), not a shared secret.

- **The private key** (`license_private_key.pem`) lives only on the
  machine that issues licenses, alongside `license_generator.py`.
  Only this key can *create* a valid signature.
- **The public key** is pasted directly into
  `electro_stock_inventory.html` (the `LICENSE_PUBLIC_KEY_B64`
  constant), in plain view in the JavaScript. This is genuinely safe:
  a public key can only *check* a signature, never create one, so
  anyone reading it gains no ability to forge their own license.

This means license verification now happens **entirely inside the
browser**, using the Web Crypto API — no server call, no Cloudflare
Worker, no dependency on which data-sync mode (Local/GitHub) a
device is using. It even works completely offline.

### One-time setup
1. Run `python license_generator.py` (needs the `cryptography`
   package: `pip install cryptography`, one machine only — no other
   device needs this).
2. First run generates a fresh keypair automatically:
   - `license_private_key.pem` — keep this file. Never share it,
     never commit it to GitHub.
   - `license_public_key.txt` — the matching public key.
3. Copy the public key into `electro_stock_inventory.html`:
   ```js
   const LICENSE_PUBLIC_KEY_B64 = '';
   ```
   becomes
   ```js
   const LICENSE_PUBLIC_KEY_B64 = 'BB4g/CFCFHIQwnLmTyEc...(your key)';
   ```
4. Re-upload the HTML anywhere it's deployed (GitHub Pages, or the
   copy on each PC).
5. Issue license keys anytime with `python license_generator.py`
   (option 1) — paste the resulting key string into the app's
   license screen.

### Trade-off to know about
Because verification is fully offline/client-side, there's no way to
remotely revoke a specific key after it's been issued (e.g. to cut
off one customer early) — a key stays valid until its built-in
expiry date, full stop. If you need to kill an individual license
before its expiry, you'd need a different (server-checked) design.
For "paid once, works until it expires," this trade-off is a good
one — no server to keep running, nothing that can go offline.

### If you were previously using the old HMAC secret
Any license keys issued under the old system (`license_secret.json`,
HMAC-SHA256) will **stop validating** after this switch — the
verification algorithm itself changed, not just where it runs.
Re-issue any keys you'd already given out using the new generator.
`license_secret.json` is no longer used anywhere and can be deleted.

## Remote license verifier (Cloudflare Worker) — no longer needed

`cloudflare_worker.js` was built for the previous (HMAC secret)
system, to give devices with no local server a way to verify
licenses. With public-key verification, every device can verify
locally in the browser, so this file is now unused — see the
deprecation notice at the top of that file. Safe to delete from your
Cloudflare dashboard if you'd already deployed it.

## Default admin password — removed

Every fresh install shows a "Create your admin account" screen where
you choose your own username and password before anything else
works. No known default credentials exist.

## General rule for anything added to this repo going forward

Nothing that must stay secret (private keys, tokens, passwords)
should ever be hardcoded into `electro_stock_inventory.html` or any
other file that gets committed to GitHub — that file is, by
definition, fully public once deployed. Anything secret belongs in a
local, gitignored file instead (`license_private_key.pem`,
`electro_sync_config.json`, and each device's own GitHub personal
access token, which lives only in that browser's local storage).
