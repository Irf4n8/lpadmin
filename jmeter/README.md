# MAM JMeter race plan

`MAM_Production_Race_Test_Plan.jmx` contains two stages:

1. A read-only preflight that logs in, confirms `real` + `hedging`, and requires the master account to be flat.
2. A two-thread duplicate-delivery race using the same `request_id` and `group_id`. This stage is disabled unless `enable_writes=true` is supplied. Each thread closes the position it created and the plan verifies cleanup.

No password or live URL is stored in the plan. Supply them as JMeter properties. Use only the dedicated simulated accounts.

## GUI setup

1. Open JMeter and load `MAM_Production_Race_Test_Plan.jmx`.
2. Set the properties in `user.properties`, or start JMeter with `-J` parameters.
3. Run the read-only preflight first with write testing disabled.
4. Review the preflight results and confirm the master is flat.
5. Enable the write race only for the authorized test environment.

## Non-GUI execution

PowerShell example:

```powershell
jmeter -n `
  -t jmeter/MAM_Production_Race_Test_Plan.jmx `
  -Jprotocol=https `
  -Jhost=YOUR_TEST_HOST `
  -Jmaster_email=mamm@mailinator.com `
  -Jmember_password=YOUR_TEST_PASSWORD `
  -Jenable_writes=true `
  -Jrace_request_id=jm_retry_$([guid]::NewGuid().ToString('N')) `
  -Jrace_group_id=jm_group_$([guid]::NewGuid().ToString('N')) `
  -l reports/jmeter/mam-race-results.jtl `
  -e -o reports/jmeter/html
```

Omit `-Jenable_writes=true` to run only the read-only stage. Use a fresh `race_request_id`, `race_group_id`, JTL file, and empty HTML output directory for every execution.

The key assertion is **Exactly one position for stable request identity**. A failure means the two identical deliveries created zero or multiple master positions. The cleanup assertion must still pass.
