#!/usr/bin/env python3
"""
Generates tests/jmeter/blacktrader_oms_load_test.jmx  (Apache JMeter 5.6.x test plan).

Everything tunable is a JMeter property (-Jname=value) so the same plan serves every load profile:
  HOST PORT PROTOCOL INSTANCE SYMBOL ORDER_QTY THINK_MS RAMP
  AUTH_THREADS AUTH_LOOPS  ORDER_THREADS ORDER_LOOPS  READ_THREADS READ_DURATION  HIST_THREADS HIST_LOOPS
  MASTER_TOKEN  MEMBER_PASSWORD  FOLLOWERS_CSV (email,token per line)

Run it through test_suite/jmeter_real_runner.py (creates tokens, runs JMeter, gates SLAs, audits state).
Regenerate after editing:  python tests/jmeter/build_plan.py
"""
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).with_name("blacktrader_oms_load_test.jmx")


def P(name, default):                       # JMeter property with default
    return "${__P(%s,%s)}" % (name, default)


def hdr(pairs):
    items = "".join(
        f'<elementProp name="" elementType="Header"><stringProp name="Header.name">{escape(k)}</stringProp>'
        f'<stringProp name="Header.value">{escape(v)}</stringProp></elementProp>' for k, v in pairs)
    return (f'<HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="Headers" enabled="true">'
            f'<collectionProp name="HeaderManager.headers">{items}</collectionProp></HeaderManager><hashTree/>')


def sampler(name, method, path, body=None, children=""):
    if body is None:
        args = ('<elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" '
                'testclass="Arguments" testname="User Defined Variables" enabled="true"><collectionProp name="Arguments.arguments"/></elementProp>')
        raw = "false"
    else:
        args = ('<elementProp name="HTTPsampler.Arguments" elementType="Arguments"><collectionProp name="Arguments.arguments">'
                '<elementProp name="" elementType="HTTPArgument"><boolProp name="HTTPArgument.always_encode">false</boolProp>'
                f'<stringProp name="Argument.value">{escape(body)}</stringProp><stringProp name="Argument.metadata">=</stringProp>'
                '</elementProp></collectionProp></elementProp>')
        raw = "true"
    return (f'<HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="{escape(name)}" enabled="true">'
            f'<boolProp name="HTTPSampler.postBodyRaw">{raw}</boolProp>{args}'
            f'<stringProp name="HTTPSampler.path">{escape(path)}</stringProp><stringProp name="HTTPSampler.method">{method}</stringProp>'
            '<boolProp name="HTTPSampler.follow_redirects">false</boolProp><boolProp name="HTTPSampler.use_keepalive">true</boolProp>'
            f'<boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp></HTTPSamplerProxy><hashTree>{children}</hashTree>')


def code_assert(code, name=None, ignore_status=False):
    return (f'<ResponseAssertion guiclass="AssertionGui" testclass="ResponseAssertion" testname="{name or "HTTP " + str(code)}" enabled="true">'
            f'<collectionProp name="Asserion.test_strings"><stringProp name="1">{code}</stringProp></collectionProp>'
            '<stringProp name="Assertion.custom_message"></stringProp><stringProp name="Assertion.test_field">Assertion.response_code</stringProp>'
            f'<boolProp name="Assertion.assume_success">{"true" if ignore_status else "false"}</boolProp><intProp name="Assertion.test_type">8</intProp>'
            '</ResponseAssertion><hashTree/>')


def json_assert(path, expected=None, name=None):
    return (f'<JSONPathAssertion guiclass="JSONPathAssertionGui" testclass="JSONPathAssertion" testname="{escape(name or "JSON " + path)}" enabled="true">'
            f'<stringProp name="JSON_PATH">{escape(path)}</stringProp><stringProp name="EXPECTED_VALUE">{escape(expected or "")}</stringProp>'
            f'<boolProp name="JSONVALIDATION">{"true" if expected else "false"}</boolProp><boolProp name="EXPECT_NULL">false</boolProp>'
            '<boolProp name="INVERT">false</boolProp><boolProp name="ISREGEX">false</boolProp></JSONPathAssertion><hashTree/>')


def extractor(var, path):
    return (f'<JSONPostProcessor guiclass="JSONPostProcessorGui" testclass="JSONPostProcessor" testname="Extract {var}" enabled="true">'
            f'<stringProp name="JSONPostProcessor.referenceNames">{var}</stringProp><stringProp name="JSONPostProcessor.jsonPathExprs">{escape(path)}</stringProp>'
            '<stringProp name="JSONPostProcessor.match_numbers">1</stringProp><stringProp name="JSONPostProcessor.defaultValues">NOT_FOUND</stringProp>'
            '</JSONPostProcessor><hashTree/>')


def timer(ms):
    return (f'<ConstantTimer guiclass="ConstantTimerGui" testclass="ConstantTimer" testname="Think time" enabled="true">'
            f'<stringProp name="ConstantTimer.delay">{ms}</stringProp></ConstantTimer><hashTree/>')


def cookies():
    return ('<CookieManager guiclass="CookiePanel" testclass="CookieManager" testname="Cookies (cleared each iteration)" enabled="true">'
            '<collectionProp name="CookieManager.cookies"/><boolProp name="CookieManager.clearEachIteration">true</boolProp>'
            '<boolProp name="CookieManager.controlledByThreadGroup">false</boolProp></CookieManager><hashTree/>')


def csv_tokens():
    return ('<CSVDataSet guiclass="TestBeanGUI" testclass="CSVDataSet" testname="Follower accounts (email,token)" enabled="true">'
            '<stringProp name="delimiter">,</stringProp><stringProp name="fileEncoding">UTF-8</stringProp>'
            f'<stringProp name="filename">{P("FOLLOWERS_CSV", "followers.csv")}</stringProp><boolProp name="ignoreFirstLine">false</boolProp>'
            '<boolProp name="quotedData">false</boolProp><boolProp name="recycle">true</boolProp><stringProp name="shareMode">shareMode.all</stringProp>'
            '<boolProp name="stopThread">false</boolProp><stringProp name="variableNames">email,token</stringProp></CSVDataSet><hashTree/>')


def thread_group(name, threads, loops=None, duration=None, ramp=P("RAMP", 5), children=""):
    sched = duration is not None
    return (f'<ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="{escape(name)}" enabled="true">'
            '<stringProp name="ThreadGroup.on_sample_error">continue</stringProp>'
            '<elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" '
            'testname="Loop Controller" enabled="true"><boolProp name="LoopController.continue_forever">false</boolProp>'
            f'<stringProp name="LoopController.loops">{"-1" if sched else loops}</stringProp></elementProp>'
            f'<stringProp name="ThreadGroup.num_threads">{threads}</stringProp><stringProp name="ThreadGroup.ramp_time">{ramp}</stringProp>'
            f'<boolProp name="ThreadGroup.scheduler">{"true" if sched else "false"}</boolProp>'
            f'<stringProp name="ThreadGroup.duration">{duration if sched else ""}</stringProp><stringProp name="ThreadGroup.delay"></stringProp>'
            f'<boolProp name="ThreadGroup.same_user_on_next_iteration">false</boolProp></ThreadGroup><hashTree>{children}</hashTree>')


def build() -> str:
    inst = "${INSTANCE}"
    master_hdr = hdr([("Authorization", "Bearer " + P("MASTER_TOKEN", "")), ("X-Broker-ID", inst)])
    follower_hdr = hdr([("Authorization", "Bearer ${token}"), ("X-Broker-ID", inst)])

    # 1) AUTH: real two-step login (cookie) then chart-token mint
    auth = thread_group("TG1 Auth: login + chart-token", P("AUTH_THREADS", 10), loops=P("AUTH_LOOPS", 3), children=(
        cookies() + csv_tokens() + timer(P("THINK_MS", 200)) +
        sampler("AUTH login", "POST", "/api/auth/login", '{"email":"${email}","password":"' + P("MEMBER_PASSWORD", "") + '"}',
                code_assert(200)) +
        sampler("AUTH chart-token", "POST", "/api/auth/chart-token", "",
                code_assert(200) + json_assert("$.token"))))

    # 2) MASTER: place market order (fans out to every follower) then close it
    orders = thread_group("TG2 Master: place + close (copy fan-out)", P("ORDER_THREADS", 10), loops=P("ORDER_LOOPS", 3), children=(
        master_hdr + timer(P("THINK_MS", 200)) +
        sampler("ORDER place market", "POST", f"/v1/oms/{inst}/orders",
                '{"symbol":"' + P("SYMBOL", "BINANCE:BTCUSDT.P") + '","side":"BUY","type":"MARKET","qty":' + P("ORDER_QTY", "0.01") + '}',
                code_assert(200) + json_assert("$.order.state", "FILLED", "order FILLED") + extractor("MID", "$.order.market_order_id")) +
        sampler("ORDER close position", "POST", f"/v1/oms/{inst}/positions/${{MID}}/squareoff", "{}",
                code_assert(200))))

    # 3) READS: followers polling their positions (what the trading UI does)
    reads = thread_group("TG3 Read: follower positions", P("READ_THREADS", 25), duration=P("READ_DURATION", 30), children=(
        csv_tokens() + follower_hdr + timer(P("THINK_MS", 200)) +
        sampler("READ positions", "GET", f"/v1/oms/{inst}/positions", None, code_assert(200) + json_assert("$.success", "true", "success=true"))))

    # 4) HISTORY: unpaginated order list (heavy payload)
    hist = thread_group("TG4 Read: order history (unpaginated)", P("HIST_THREADS", 3), loops=P("HIST_LOOPS", 3), children=(
        csv_tokens() + follower_hdr + timer(P("THINK_MS", 200)) +
        sampler("READ orders (history)", "GET", f"/v1/oms/{inst}/orders", None, code_assert(200))))

    # 5) NEGATIVE: invalid input must be rejected with 4xx (labels start with 'NEG ')
    def neg(name, body, code=400, extra=""):
        return sampler(name, "POST", f"/v1/oms/{inst}/orders", body, code_assert(code, f"expects {code}", ignore_status=True) + extra)
    s = P("SYMBOL", "BINANCE:BTCUSDT.P")
    negative = thread_group("TG5 Negative: invalid input is rejected", 1, loops=1, children=(
        master_hdr +
        neg("NEG zero qty", '{"symbol":"' + s + '","side":"BUY","type":"MARKET","qty":0}') +
        neg("NEG negative qty", '{"symbol":"' + s + '","side":"BUY","type":"MARKET","qty":-1}') +
        neg("NEG string qty", '{"symbol":"' + s + '","side":"BUY","type":"MARKET","qty":"abc"}') +
        neg("NEG missing symbol", '{"side":"BUY","type":"MARKET","qty":1}') +
        neg("NEG bad side", '{"symbol":"' + s + '","side":"HOLD","type":"MARKET","qty":1}') +
        neg("NEG unknown order type", '{"symbol":"' + s + '","side":"BUY","type":"WEIRD","qty":1}') +
        neg("NEG absurd tp/sl", '{"symbol":"' + s + '","side":"BUY","type":"MARKET","qty":0.01,"tp":-1,"sl":1e30}',
            extra=extractor("MID_NEG", "$.order.market_order_id")) +
        # if the platform wrongly ACCEPTED the absurd order it opened a real position - close it (label CLEANUP is not gated)
        sampler("CLEANUP close accepted invalid order", "POST", f"/v1/oms/{inst}/positions/${{MID_NEG}}/squareoff", "{}",
                code_assert(200, "ignore", ignore_status=True))))

    udv = "".join(
        f'<elementProp name="{k}" elementType="Argument"><stringProp name="Argument.name">{k}</stringProp>'
        f'<stringProp name="Argument.value">{v}</stringProp><stringProp name="Argument.metadata">=</stringProp></elementProp>'
        for k, v in [("HOST", P("HOST", "lpadmin.blackfx.com")), ("PORT", P("PORT", 443)), ("PROTOCOL", P("PROTOCOL", "https")),
                     ("INSTANCE", P("INSTANCE", "paper"))])
    defaults = ('<ConfigTestElement guiclass="HttpDefaultsGui" testclass="ConfigTestElement" testname="HTTP Request Defaults" enabled="true">'
                '<elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" '
                'testname="User Defined Variables" enabled="true"><collectionProp name="Arguments.arguments"/></elementProp>'
                '<stringProp name="HTTPSampler.domain">${HOST}</stringProp><stringProp name="HTTPSampler.port">${PORT}</stringProp>'
                '<stringProp name="HTTPSampler.protocol">${PROTOCOL}</stringProp><stringProp name="HTTPSampler.contentEncoding">UTF-8</stringProp>'
                '<stringProp name="HTTPSampler.path"></stringProp><stringProp name="HTTPSampler.connect_timeout">8000</stringProp>'
                '<stringProp name="HTTPSampler.response_timeout">30000</stringProp></ConfigTestElement><hashTree/>')
    plan_hdr = hdr([("Content-Type", "application/json"), ("Accept", "application/json"), ("User-Agent", "BlackTrader-JMeter-LoadTest")])

    return ('<?xml version="1.0" encoding="UTF-8"?>\n<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3"><hashTree>'
            '<TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="BlackTrader OMS Load Test" enabled="true">'
            '<stringProp name="TestPlan.comments">Generated by tests/jmeter/build_plan.py - run via test_suite/jmeter_real_runner.py</stringProp>'
            '<boolProp name="TestPlan.functional_mode">false</boolProp><boolProp name="TestPlan.tearDown_on_shutdown">true</boolProp>'
            '<boolProp name="TestPlan.serialize_threadgroups">true</boolProp>'
            '<elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" '
            f'testname="User Defined Variables" enabled="true"><collectionProp name="Arguments.arguments">{udv}</collectionProp></elementProp>'
            '<stringProp name="TestPlan.user_define_classpath"></stringProp></TestPlan><hashTree>'
            + plan_hdr + defaults + auth + orders + reads + hist + negative +
            '</hashTree></hashTree></jmeterTestPlan>\n')


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print("wrote", OUT)
