# MAM Category Manager

Unified script to dynamically switch MAM follower accounts between the three supported allocation categories:
1. **Multiplier** (e.g., 2.0x, 1.5x, 3.0x)
2. **Equity Based** (proportional to Follower Equity / Master Balance)
3. **Balance Based** (proportional to Follower Balance / Master Balance)

---

## Usage

```powershell
# 1. Switch to Multiplier (2.0x)
python mam_management/change_mam_category.py --category multiplier --multiplier 2.0

# 2. Switch to Equity Based
python mam_management/change_mam_category.py --category equity

# 3. Switch to Balance Based
python mam_management/change_mam_category.py --category balance

# 4. Target a custom master or custom follower range
python mam_management/change_mam_category.py --master "newmaster@test.com" --start 1 --end 50 --category multiplier --multiplier 1.5

# 5. Target specific account list
python mam_management/change_mam_category.py --followers "acc1@test.com,acc2@test.com" --category equity
```

## Features
- **Dynamic Master**: Accepts master email or client ID; resolves automatically.
- **Dynamic Followers**: Supports range (`--start`/`--end`), comma-separated list (`--followers`), or file (`--file`).
- **Auto-Unfollow**: Leaves existing active MAM follow link cleanly before establishing the new category.
- **Concurrency**: High-throughput multi-threaded processing (20 workers) completes 100 accounts in ~2-3 seconds.
- **Verification**: Validates active follow status directly against OMS API.

