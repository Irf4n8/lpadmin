# Social-Trading Feature Evidence Report

**Generated:** 2026-11-13T05:09:05.892505+00:00

| Scenario | Result | Detail |
| :--- | :---: | :--- |
| F1 Instances | ❌ FAIL | admin and user instance lists agree (admin ['binance', 'coinbase', 'paper', 'paper-net', 'real', 'real-net', 'zerodha']); all instances enabled + visible {'paper': (True, True), 'real': (True, True), 'paper-net': (True, True), 'real-net': (True, True), 'binance': (False, False), 'zerodha': (False, False), 'coinbase': (False, False)}; admin product matches mode {'paper': 'papertrade_gross', 'real': 'whitelabel_gross', 'paper-net': 'papertrade_net', 'real-net': 'whitelabel_net', 'binance': 'papertrade_gross', 'zerodha': 'papertrade_gross', 'coinbase': 'papertrade_gross'} |
| F2 Master directories | ❌ FAIL | copy: masters are kind=copy_manager {'private_master', 'copy_manager'} |
| F3 Role exclusivity | ✅ PASS | 8 checks passed |
| F4 Relationship shape | ✅ PASS | 10 checks passed |
| F5 Auth enforcement | ❌ FAIL | anonymous /_instances refused (got 200) |
| F6 Money / IB / portal reads | ✅ PASS | 9 checks passed |
| F7 Invalid writes rejected | ✅ PASS | 9 checks passed |
| F8 Admin config | ❌ FAIL | EXC KeyError: 'balances' |

## Every check

### F1 Instances
- ✅ 4 instances exist (paper, paper-net, real, real-net)
- ✅ paper: mode matches netting flag
- ✅ paper: real_money flag follows the name
- ✅ paper: hedging/netting follows the -net suffix
- ✅ real: mode matches netting flag
- ✅ real: real_money flag follows the name
- ✅ real: hedging/netting follows the -net suffix
- ✅ paper-net: mode matches netting flag
- ✅ paper-net: real_money flag follows the name
- ✅ paper-net: hedging/netting follows the -net suffix
- ✅ real-net: mode matches netting flag
- ✅ real-net: real_money flag follows the name
- ✅ real-net: hedging/netting follows the -net suffix
- ✅ admin /instances reachable
- ❌ admin and user instance lists agree (admin ['binance', 'coinbase', 'paper', 'paper-net', 'real', 'real-net', 'zerodha'])
- ❌ all instances enabled + visible {'paper': (True, True), 'real': (True, True), 'paper-net': (True, True), 'real-net': (True, True), 'binance': (False, False), 'zerodha': (False, False), 'coinbase': (False, False)}
- ❌ admin product matches mode {'paper': 'papertrade_gross', 'real': 'whitelabel_gross', 'paper-net': 'papertrade_net', 'real-net': 'whitelabel_net', 'binance': 'papertrade_gross', 'zerodha': 'papertrade_gross', 'coinbase': 'papertrade_gross'}

### F2 Master directories
- ✅ copy: directory returns masters
- ✅ copy: no duplicate masters
- ✅ copy: every master has id, name and full stats ['curve', 'drawdown', 'followers', 'fund', 'growth', 'rank', 'risk_level', 'trades', 'weeks']
- ✅ copy: ranks sorted ascending
- ✅ copy: no negative drawdown/followers
- ✅ mam: directory returns masters
- ✅ mam: no duplicate masters
- ✅ mam: every master has id, name and full stats ['curve', 'drawdown', 'followers', 'fund', 'growth', 'rank', 'risk_level', 'trades', 'weeks']
- ✅ mam: ranks sorted ascending
- ✅ mam: no negative drawdown/followers
- ✅ mam: share_percent present and within 0..100
- ✅ pamm: directory returns masters
- ✅ pamm: no duplicate masters
- ✅ pamm: every master has id, name and full stats ['curve', 'drawdown', 'followers', 'fund', 'growth', 'rank', 'risk_level', 'trades', 'weeks']
- ✅ pamm: ranks sorted ascending
- ✅ pamm: no negative drawdown/followers
- ✅ pamm: share_percent present and within 0..100
- ✅ master directory is the same for master and follower views
- ❌ copy: masters are kind=copy_manager {'private_master', 'copy_manager'}

### F3 Role exclusivity
- ✅ mam/follows reachable for the copy master
- ✅ mam: master gets follow_blocked_reason ('can't follow another master')
- ✅ pamm/follows reachable for the copy master
- ✅ pamm: master gets follow_blocked_reason ('can't follow another master')
- ✅ mam/follows reachable for a follower
- ✅ follower has no follow block
- ✅ mam: follower follower100 is blocked from becoming a master
- ✅ pamm: follower follower100 is blocked from becoming a master

### F4 Relationship shape
- ✅ copy/follows reachable
- ✅ copy/follows lists the master's followers
- ✅ every link carries the full field set
- ✅ link instances are valid slugs
- ✅ link statuses are known
- ✅ methods are multiplier|balance|equity
- ✅ copy_mode is public|private
- ✅ one link record per follower (no duplicates)
- ✅ mam/follows has keys ['follow_blocked_reason', 'followers', 'following', 'is_master', 'master', 'master_blocked_reason']
- ✅ pamm/follows has keys ['follow_blocked_reason', 'is_master', 'master', 'master_blocked_reason', 'pool', 'pool_history', 'pool_total', 'subscriptions']

### F5 Auth enforcement
- ✅ anonymous GET /copy/masters refused
- ✅ anonymous GET /copy/follows refused
- ✅ anonymous GET /mam/masters refused
- ✅ anonymous GET /mam/follows refused
- ✅ anonymous GET /pamm/masters refused
- ✅ anonymous GET /pamm/follows refused
- ✅ anonymous GET /wallets refused
- ✅ anonymous GET /portal/summary refused
- ✅ anonymous GET /ib/summary refused
- ✅ anonymous GET /portal/transfers refused
- ✅ anonymous POST /copy/follow refused
- ✅ anonymous POST /mam/follow refused
- ✅ anonymous POST /pamm/join refused
- ✅ anonymous POST /copy/master refused
- ✅ anonymous POST /wallets/transfer refused
- ❌ anonymous /_instances refused (got 200)

### F6 Money / IB / portal reads
- ✅ GET /wallets -> JSON 200
- ✅ GET /wallets/history?limit=5 -> JSON 200
- ✅ GET /portal/summary -> JSON 200
- ✅ GET /portal/history?limit=5 -> JSON 200
- ✅ GET /portal/transfers?limit=5 -> JSON 200
- ✅ GET /portal/payout-methods -> JSON 200
- ✅ GET /ib/summary -> JSON 200
- ✅ GET /ib/payouts?limit=5 -> JSON 200
- ✅ GET /ib/downline?limit=5 -> JSON 200

### F7 Invalid writes rejected
- ✅ copy follow, unknown master rejected with 4xx
- ✅ copy follow, bad method rejected with 4xx
- ✅ copy follow, negative multiplier rejected with 4xx
- ✅ mam follow, unknown master rejected with 4xx
- ✅ pamm join, unknown master rejected with 4xx
- ✅ pamm join, negative deposit rejected with 4xx
- ✅ copy unfollow, unknown master rejected with 4xx
- ✅ no relationship was created by the rejected writes
- ✅ follower1 still has no active link anywhere

### F8 Admin config
- ✅ admin /groups reachable
- ✅ a default group exists
- ✅ groups carry brokerage, markup, ib and margin settings
- ✅ IB levels are percentages
- ✅ admin /config reachable
- ✅ plans defined: free, basic, premium, pro
- ✅ premium plan includes ['copytrading', 'ib', 'mam', 'pamm', 'wallet']
- ✅ pro plan includes ['copytrading', 'ib', 'mam', 'pamm', 'wallet']
- ✅ free plan has no social-trading modules
- ✅ basic plan has no social-trading modules
- ✅ admin /deposits reachable
- ✅ admin /withdrawals reachable
- ✅ admin /kyc reachable
- ✅ member rows expose book, plan, group_code, allowed_modules, balances
- ❌ EXC KeyError: 'balances'

