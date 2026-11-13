# Platform feature map (as crawled 2026-11-13)

What `lpadmin.blackfx.com` offers today, how it is reached through the API, and which suite covers it.
Re-crawl with `python scripts/crawl_platform.py` (logs in with a browser and lists every request the workspace makes)
if the platform changes again - the dashboard's **Platform** tab shows the live state without a crawl.

## Architecture
* `lpadmin.blackfx.com` is a thin shell (login, register, account, dashboard). The trading workspace is an iframe served from
  `chartv2.blacktrader.com` that talks to `lpadmin.blackfx.com/v1/oms/...`.
* Auth: `POST /api/auth/login` (cookie) + `POST /api/auth/chart-token` (opaque Bearer for `/v1/oms`). Admin: `POST /admin/api/login`.
* Public: `/api/config` (brand, oms domain, **broker token**) and `/v1/oms/_instances` (instance names/modes). Everything else needs a token.

## Four trading instances
| slug | name | position mode | wallet | admin product |
| --- | --- | --- | --- | --- |
| `paper` | Paper (Hedging) | hedging - every order is its own position | simulated | `papertrade_gross` |
| `paper-net` | Paper (Netting) | netting - one position per symbol; opposite orders reduce / flip | simulated | `papertrade_net` |
| `real` | Real (Hedging) | hedging | real-money wallet | `whitelabel_gross` |
| `real-net` | Real (Netting) | netting | real-money wallet | `whitelabel_net` |

Every OMS route is `/v1/oms/<slug>/...`. Balances are per instance (`balances: {paper, paper-net, real, real-net}` on the admin member row).
Three more instances (`binance`, `zerodha`, `coinbase`) exist in admin but are disabled/hidden.

## Social trading: three modes
All three have the same shape: `GET /<kind>/masters` (directory), `GET /<kind>/follows` (my relationships), `POST /<kind>/follow|unfollow|master`.

| Mode | Directory | Follow body | Become master body | Notes |
| --- | --- | --- | --- | --- |
| **Standard copy** `/copy/*` | `masters[]` with `kind` = `copy_manager` or `private_master` | `{master_client_id, method: multiplier\|balance\|equity, multiplier, reverse, copy_mode: public\|private}` | `{kind, display_name}` | the mode the existing suites test |
| **MAM** `/mam/*` | adds `share_percent` | `{master_client_id, method, multiplier}` | `{display_name, share_percent}` | `GET /mam/shares?role=master` for profit shares |
| **PAMM** `/pamm/*` | adds `share_percent` | `POST /pamm/join {master_client_id, deposit}` | `{display_name, share_percent}` | pooled money: join/unfollow are async "money operations" (`/money/operations/<id>`), unfollow settles `payout` + `master_share`; `GET /pamm/allocations` |

Directory stats per master: `rank, growth, curve[], weeks, followers, drawdown, fund, risk_level, trades`.

**Rules the platform enforces**
* A **master cannot follow** another master; an account that **follows cannot become a master** (`follow_blocked_reason` / `master_blocked_reason` on `/<kind>/follows`).
* **A follower has ONE link record per master, whatever the instance.** `follow` on another instance *converts* the existing link (instance + multiplier change); `unfollow` then ends it.
* **Paper copy links can no longer be created** (HTTP 400 "Copy trading, MAM and PAMM run on real-money accounts. A paper relationship that already exists can still be ended here."). Ending one is permanent.
* Plans gate modules: `free`/`basic` have none of `copytrading, mam, pamm, ib, wallet, alerts, algo, backtest`; `premium`/`pro` have them.

## Other new areas
| Area | Endpoints (user) | Endpoints (admin) |
| --- | --- | --- |
| Wallets | `/wallets`, `/wallets/history`, `POST /wallets/transfer` | `/admin/api/members/<id>/balance` |
| Money portal | `/portal/summary`, `/portal/history`, `/portal/transfers`, `/portal/deposits`, `/portal/withdrawals` (+OTP), `/portal/payout-methods`, `/portal/methods` | `/admin/api/deposits`, `/withdrawals` |
| KYC | `/portal/documents` (upload slots) | `/admin/api/kyc` |
| IB / referral | `/ib/summary`, `/ib/payouts`, `/ib/downline`, `POST /ib/referrer {referral_code}` | groups carry `ib {enabled, mode, levels:[30,15,10]}` |
| Groups | - | `/admin/api/groups` (brokerage, markup bps, margin %, leverage, symbol overrides) |
| Instances | `/_instances` | `/admin/api/instances` |
| Market / alerts | `/<slug>/market/extremes`, `/<slug>/alerts/events` | - |
| Account | `/<slug>/account?symbol=&terms=resolved` | member `book` (`a`/`b`), `plan`, `allowed_modules` |

## Coverage
| Feature | Suite (dashboard key) | Status |
| --- | --- | --- |
| Standard copy, hedging (`paper`) - sizing, TP/SL, partial, pending, races, accounting | multiplier, balance, equity, symmetry, copy_complex, e2e, race, breakpoint, accounting, jmeter | covered |
| Netting vs hedging, master + copy (`paper`, `paper-net`, `real`, `real-net`) | `netting_paper`, `netting_real` | covered (copy on `real`/`real-net` only; no paper links possible) |
| Directories, role rules, link shape, auth, invalid writes, admin config, IB/wallet/portal reads | `social_features` | covered (read-mostly) |
| MAM / PAMM **trading** (profit share, pool settlement, allocations) | - | **not covered**: needs a dedicated money-moving suite and a go-ahead |
| Deposits / withdrawals / KYC upload / payout methods | - | **not covered** (money + documents) |
| IB payouts / downline math | - | not covered beyond read contract |
| Alerts, screener, algo, backtest, coder | - | not covered |

## Known findings (open)
1. `real-net`: TP/SL set on the master is **not copied** to followers, and **pending orders are not copied** (0/6 after 30 s). Hedging (`real`) copies both.
2. Order entry: unknown order type returns HTTP 500; absurd TP/SL (`tp=-1, sl=1e30`) accepted.
3. `GET /orders` is unpaginated: p95 6.7 s (standard) / 12.8 s (stress) vs a 6 s SLA.
4. Master `ctmaster` flipped from B-book to A-book during testing (not by the test suites).
