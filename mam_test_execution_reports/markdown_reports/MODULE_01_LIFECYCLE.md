# Module 1: Group & Sub-Account Lifecycle

Rewritten from live evidence. No release sign-off.

## MAM-F001 — Create Master MAM Group

Status: **BLOCKED**

Existing authorized master verified; creation of a new master group and MT5/FIX binding were not performed.

Evidence checks: None; blocked

## MAM-F002 — Configure Manager Performance Fee and Allocation Profile

Status: **PARTIAL**

Fee update/readback/restore tested; monthly crystallization and allocation-profile workflow not verified.

Evidence checks: MAM-FEE-CONFIG

## MAM-F003 — Digital Limited Power of Attorney (LPOA) Contract Signing

Status: **BLOCKED**

LPOA contracts, independent group-management/archival controls or required role fixtures are not available in the verified API/UI flow.

Evidence checks: None; blocked

## MAM-F004 — Link Sub-Account to MAM Master Group

Status: **PARTIAL**

API leave/rejoin tested; signed LPOA and Bound_Active rights-transfer workflow not verified.

Evidence checks: MAM-UNFOLLOW-FLAT, MAM-JOIN-MIDTRADE

## MAM-F005 — Link Sub-Account Below Minimum Balance Threshold

Status: **PARTIAL**

Zero-capital trade rejection tested; a configured minimum-balance JOIN threshold was not established.

Evidence checks: MARGIN-ISOLATION

## MAM-F006 — Switch MAM Allocation Method on Active Group

Status: **PARTIAL**

Balance/equity sizing on current MAM tested; immutable configuration audit trail not inspected.

Evidence checks: SIZE-BALANCE, SIZE-EQUITY

## MAM-F007 — Switch Allocation Method While Positions Are Open

Status: **PARTIAL**

Future-vs-existing sizing tested; original group allocation-profile transition differs from these follower settings.

Evidence checks: MAM-MULTIPLIER-MIDTRADE, GUI-BALANCE-NEXT-ORDER

## MAM-F008 — Multi-Currency Sub-Account Inclusion (USD, EUR, GBP in One Group)

Status: **BLOCKED**

LPOA contracts, independent group-management/archival controls or required role fixtures are not available in the verified API/UI flow.

Evidence checks: None; blocked

## MAM-F009 — Group Maximum Capacity Cap Gating

Status: **BLOCKED**

LPOA contracts, independent group-management/archival controls or required role fixtures are not available in the verified API/UI flow.

Evidence checks: None; blocked

## MAM-F010 — Sub-Account Voluntary Disconnection (Revoking LPOA) With Zero Trades

Status: **PARTIAL**

Unfollow prevents new copies; LPOA revocation, Independent status and manager notification not verified.

Evidence checks: MAM-UNFOLLOW-FLAT

## MAM-F011 — Sub-Account Disconnection Request While Positions Are Open

Status: **PARTIAL**

Open/unfollow ordering observed; no contractual close-or-transfer selection workflow was established.

Evidence checks: RACE-UNFOLLOW-OPEN-1, RACE-UNFOLLOW-OPEN-2, RACE-UNFOLLOW-OPEN-3

## MAM-F012 — Manager Pause / Resume of Individual Sub-Account Participation

Status: **BLOCKED**

LPOA contracts, independent group-management/archival controls or required role fixtures are not available in the verified API/UI flow.

Evidence checks: None; blocked

## MAM-F013 — Multi-Group Manager Configuration

Status: **BLOCKED**

LPOA contracts, independent group-management/archival controls or required role fixtures are not available in the verified API/UI flow.

Evidence checks: None; blocked

## MAM-F014 — Sub-Account Direct Trading Prevention (LPOA Lockout)

Status: **PARTIAL**

Current platform permits independent follower trades. Original LPOA direct-trading lockout requirement is not demonstrated.

Evidence checks: ISOLATE-MANUAL-FOLLOWER

## MAM-F015 — Manager Voluntary Group Archival / Dissolution

Status: **BLOCKED**

LPOA contracts, independent group-management/archival controls or required role fixtures are not available in the verified API/UI flow.

Evidence checks: None; blocked

