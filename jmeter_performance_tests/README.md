# JMeter Performance Testing Guide for BlackTrader

This directory contains ready-to-run Apache JMeter test plans, runner scripts, and automated HTML reporting for performance and load testing.

---

## 1. Environment & Paths Detected

- **JMeter Location:** `C:\Users\Asus\Downloads\apache-jmeter-5.6.3\apache-jmeter-5.6.3\bin\jmeter.bat`
- **Java Home:** `C:\Program Files\Java\jdk-25.0.5.0.3`

---

## 2. Included Test Plans

1. **`dashboard_load_test.jmx`**:
   - Tests the local real-time QA & monitoring dashboard (`http://127.0.0.1:8500`).
   - Measures response times, throughput, and concurrent request handling for UI (`/`) and API data (`/api/data?master=mam`).
   - Supports parameterization (`threads`, `loops`, `rampup`, `host`, `port`).

2. **`blacktrader_api_test.jmx`**:
   - Tests the remote BlackTrader LPAdmin endpoints (`https://lpadmin.blackfx.com`).
   - Authenticates via `/admin/api/login`, extracts the bearer token, and stress tests `/admin/api/members`.
   - Supports parameters (`threads`, `loops`, `rampup`, `base_url`, `admin_email`, `admin_password`).

---

## 3. How to Run the Tests

### Option A: 1-Click Execution (Headless CLI + HTML Report)
Run the script in the project root:
```cmd
run_performance_test.bat
```
This executes the test, logs metrics into a `.jtl` file, compiles an interactive HTML dashboard report, and opens it directly in your web browser.

### Option B: Interactive JMeter GUI Mode
To open the graphical JMeter interface to edit, add samplers, or inspect live trees:
```cmd
run_jmeter_gui.bat
```
In the GUI:
1. Click **File -> Open**.
2. Select `jmeter_performance_tests\dashboard_load_test.jmx` or `blacktrader_api_test.jmx`.
3. Click the green **Start** button (or press `Ctrl + R`).

### Option C: Custom CLI Execution with Arguments
Run directly via PowerShell:
```powershell
$env:JAVA_HOME = "C:\Program Files\Java\jdk-25.0.5.0.3"
$env:Path = "$env:JAVA_HOME\bin;" + $env:Path
$jmeter = "C:\Users\Asus\Downloads\apache-jmeter-5.6.3\apache-jmeter-5.6.3\bin\jmeter.bat"

# Example: 25 concurrent users, 10 loops, 5-second ramp-up
& $jmeter -n -t "jmeter_performance_tests\dashboard_load_test.jmx" -l "jmeter_performance_tests\custom_results.jtl" -e -o "jmeter_performance_tests\custom_html_report" -Jthreads=25 -Jloops=10 -Jrampup=5
```

---

## 4. Key Metrics in the HTML Report

- **Throughput (Transactions/sec):** Rate of requests the system sustains under load.
- **Average & 90th / 95th Percentile Response Time:** Response latency experienced by 90-95% of users.
- **Error Rate (%):** Failed connections or HTTP status codes >= 400.
