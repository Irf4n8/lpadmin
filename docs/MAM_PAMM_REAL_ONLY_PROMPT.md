# Prompt: real-only master + followers (Copy, MAM, PAMM)

Paste everything below the line into Claude Code (or any coding assistant) in a folder that contains
`scripts/social_real_only.py`. Replace the `<...>` values first. Never paste real passwords into the chat:
put them in environment variables or a git-ignored `.env`.

---

You are helping me manage a **staging** BlackTrader / lpadmin setup. I run a **<COPY | MAM | PAMM>** master and
**<N>** followers. I want the master and every follower to trade on **one instance only**, with the other three
wallets set to zero, and I want every step verified, not assumed.

## My setup
- Platform: `https://lpadmin.blackfx.com` (staging)
- Master: `<master email>`   Followers: `<prefix>1@<domain>` … `<prefix>N@<domain>`
- Mode: `<copy | mam | pamm>`   Target instance: `<real | real-net | paper | paper-net>`
- Credentials are in environment variables: `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `MEMBER_PASSWORD`, `MASTER_EMAIL`,
  `FOLLOWER_PREFIX`, `FOLLOWER_DOMAIN`, `FOLLOWER_COUNT`. Do not print them, log them or commit them.

## Platform facts (verified, do not re-guess)
1. Instances: `paper`, `paper-net` (practice) and `real`, `real-net` (real-money wallets; hedging / netting).
   Wallets are per instance on the admin member row: `balances: {paper, paper-net, real, real-net}`.
2. Wallet writes: `POST /admin/api/members/<member_id>/balance` with
   `{"instance": "...", "balance": N, "force": true}`. Reading back through `GET /admin/api/members` is the proof.
3. A follower has **one** link record per master, whatever the instance. `follow` on another instance **moves**
   the link; calling `unfollow` afterwards **ends** it. Never unfollow after moving.
4. Paper copy / MAM / PAMM links can no longer be created (HTTP 400 "run on real-money accounts"). Ending a
   paper link is permanent.
5. A master cannot follow another master; an account that follows cannot become a master.
6. MAM: `/mam/masters` (has `share_percent`), `/mam/follows`, follow body `{master_client_id, method, multiplier}`.
   PAMM: `/pamm/masters`, `/pamm/follows` (`pool`, `subscriptions`), join body `{master_client_id, deposit}`;
   joins and unfollows are **async money operations** (`/money/operations/<id>`), poll until settled.
7. **The "Enable <instance>" checkbox in Broker Settings is saved only in each browser's `localStorage`.** There is
   no server call, so it cannot be changed in bulk by a script on the server. The server-side equivalent is the
   wallet: an instance with balance 0 cannot trade.

## What I want you to do
1. **Read first.** Run `python scripts/social_real_only.py check --kind <kind>` and show me the result: links per
   instance, wallets per instance, open positions. Do not change anything yet.
2. **Plan.** Run `python scripts/social_real_only.py fund-only --instance <target>` (dry run) and show the plan.
3. **Ask me to confirm** before any write. Money writes need my explicit "yes".
4. **Apply** with `--flatten --apply --type-confirm REAL`. `--flatten` closes open positions and cancels orders
   first; wallets with open positions can misbehave.
5. **Verify by read-back**, never by the HTTP 200. Re-run `check`. Every account must show the target instance at
   the chosen amount and the other three at 0, links on the target instance only, nothing open elsewhere.
6. **Report honestly**: how many accounts verified, which failed and why. If something looks wrong, stop and tell me.

## Rules
- Dry run by default. No writes without `--apply`. Real wallets need `--type-confirm REAL`.
- Test on one follower first if anything is unclear, then the rest.
- If wallets change that you did not touch, tell me; someone else (or the dashboard) may be changing them too.
- Do not guess write endpoints on the live platform. If you need one you do not know, ask me for the request from
  the browser's Network tab (URL, method, body).
- For MAM / PAMM, do not move money (joins, deposits, unfollows) without a separate explicit go-ahead.
- End with a short summary: what changed, what was verified, what is still open.

## Script cheat sheet
```
export BASE_URL=https://lpadmin.blackfx.com ADMIN_EMAIL=... ADMIN_PASSWORD=... MEMBER_PASSWORD=...
export MASTER_EMAIL=<master> FOLLOWER_PREFIX=<prefix> FOLLOWER_DOMAIN=<domain> FOLLOWER_COUNT=<N>

python scripts/social_real_only.py check     --kind mam
python scripts/social_real_only.py fund-only --instance real                       # dry run
python scripts/social_real_only.py fund-only --instance real --flatten --apply --type-confirm REAL
```
Amounts default to: paper 1,000,000 · paper-net 1,000,000 · real 100,000,000 · real-net 1,000,000
(`--amount` overrides; practice is capped at 10,000,000).
