@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo BlackTrader JMeter Performance Suite
echo ========================================================
echo.
echo Select Test Plan to Run:
echo   [1] Official BlackTrader OMS APIs (https://lpadmin.blackfx.com/v1/oms)
echo   [2] Local Dashboard QA Server (http://127.0.0.1:8500)
echo   [3] Admin Members API
echo.
set /p "CHOICE=Enter choice [1-3] (Default=1): "
if "%CHOICE%"=="" set "CHOICE=1"

set "JAVA_HOME=C:\Program Files\Java\jdk-25.0.5.0.3"
set "PATH=%JAVA_HOME%\bin;%PATH%"
set "JMETER=C:\Users\Asus\Downloads\apache-jmeter-5.6.3\apache-jmeter-5.6.3\bin\jmeter.bat"
set "TEST_DIR=%~dp0jmeter_performance_tests"

if "%CHOICE%"=="1" (
    set "PLAN=%TEST_DIR%\blacktrader_oms_official_apis.jmx"
    set "PLAN_NAME=OMS_APIs"
    set "EXTRA_ARGS=-Jpublic_threads=10 -Jpublic_loops=5 -Jtrader_threads=5 -Jtrader_loops=2"
) else if "%CHOICE%"=="2" (
    set "PLAN=%TEST_DIR%\dashboard_load_test.jmx"
    set "PLAN_NAME=Dashboard"
    set "EXTRA_ARGS=-Jthreads=10 -Jloops=5 -Jrampup=2"
) else (
    set "PLAN=%TEST_DIR%\blacktrader_api_test.jmx"
    set "PLAN_NAME=Admin_API"
    set "EXTRA_ARGS=-Jthreads=5 -Jloops=2 -Jrampup=2"
)

set "TIMESTAMP=%date:~10,4%%date:~4,2%%date:~7,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
set "TIMESTAMP=%TIMESTAMP: =0%"
set "RESULT_DIR=%TEST_DIR%\reports\%PLAN_NAME%_%TIMESTAMP%"
set "JTL_FILE=%RESULT_DIR%\results.jtl"
set "HTML_DIR=%RESULT_DIR%\html_report"

mkdir "%RESULT_DIR%" 2>nul

echo.
echo Running plan: %PLAN%
echo Logging to:   %RESULT_DIR%
echo.

call "%JMETER%" -n -t "%PLAN%" -l "%JTL_FILE%" -e -o "%HTML_DIR%" %EXTRA_ARGS%

echo.
echo ========================================================
echo Performance Test Completed!
echo HTML Report: %HTML_DIR%\index.html
echo ========================================================

if exist "%HTML_DIR%\index.html" (
    start "" "%HTML_DIR%\index.html"
)
pause
