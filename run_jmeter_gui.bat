@echo off
setlocal
echo ========================================================
echo Launching Apache JMeter GUI
echo ========================================================

set "JAVA_HOME=C:\Program Files\Java\jdk-25.0.5.0.3"
set "PATH=%JAVA_HOME%\bin;%PATH%"
set "JMETER_BIN=C:\Users\Asus\Downloads\apache-jmeter-5.6.3\apache-jmeter-5.6.3\bin\jmeter.bat"

if not exist "%JAVA_HOME%\bin\java.exe" (
    echo Error: Java not found at %JAVA_HOME%
    pause
    exit /b 1
)

if not exist "%JMETER_BIN%" (
    echo Error: JMeter not found at %JMETER_BIN%
    pause
    exit /b 1
)

echo Starting JMeter with Java from %JAVA_HOME% ...
start "" "%JMETER_BIN%" %*
