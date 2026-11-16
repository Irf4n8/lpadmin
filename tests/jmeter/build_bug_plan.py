#!/usr/bin/env python3
"""
Generates tests/jmeter/blacktrader_3_bugs.jmx - a small Apache JMeter plan that SHOWS the three platform bugs.

Open it in JMeter (File > Open), set EMAIL / PASSWORD in "User Defined Variables" (a TEST trader account, paper
instance), press the green Start button, then look at "View Results Tree" / "Summary Report":

    BUG-1  GET  /orders?limit=5            expected: at most 5 orders          -> RED while the platform ignores limit
    BUG-2  POST /orders  type=WEIRD        expected: HTTP 400                  -> RED while the platform answers 500
    BUG-3  POST /orders  tp=-1 sl=1e30     expected: HTTP 400, no trade        -> RED while the platform answers 200
    CONTROL  bad side                      expected: HTTP 400                  -> GREEN (proves a normal 400 works)

A red row = the bug is present. When the platform is fixed the same plan turns green.
Headless:  jmeter -n -t blacktrader_3_bugs.jmx -JEMAIL=... -JPASSWORD=... -l out.jtl -e -o html_report

No secrets are stored in the file. Everything runs on the paper instance and the trade opened by BUG-3 is closed again.
Regenerate after editing:  python tests/jmeter/build_bug_plan.py
"""
import sys
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_plan import P, hdr, sampler, code_assert, json_assert, extractor, cookies  # noqa: E402

OUT = Path(__file__).with_name("blacktrader_3_bugs.jmx")


def controller(name, children):
    return (f'<GenericController guiclass="LogicControllerGui" testclass="GenericController" testname="{escape(name)}" enabled="true"/>'
            f'<hashTree>{children}</hashTree>')


def listener(kind, name):
    gui = {"tree": "ViewResultsFullVisualizer", "summary": "SummaryReport"}[kind]
    return (f'<ResultCollector guiclass="{gui}" testclass="ResultCollector" testname="{escape(name)}" enabled="true">'
            '<boolProp name="ResultCollector.error_logging">false</boolProp><objProp><name>saveConfig</name>'
            '<value class="SampleSaveConfiguration"><time>true</time><latency>true</latency><timestamp>true</timestamp>'
            '<success>true</success><label>true</label><code>true</code><message>true</message><threadName>true</threadName>'
            '<dataType>true</dataType><encoding>false</encoding><assertions>true</assertions><subresults>true</subresults>'
            '<responseData>false</responseData><samplerData>false</samplerData><xml>false</xml><fieldNames>true</fieldNames>'
            '<responseHeaders>false</responseHeaders><requestHeaders>false</requestHeaders><responseDataOnError>false</responseDataOnError>'
            '<saveAssertionResultsFailureMessage>true</saveAssertionResultsFailureMessage><assertionsResultsToSave>0</assertionsResultsToSave>'
            '<bytes>true</bytes><sentBytes>true</sentBytes><url>true</url><threadCounts>true</threadCounts><idleTime>true</idleTime>'
            '<connectTime>true</connectTime></value></objProp><stringProp name="filename"></stringProp></ResultCollector><hashTree/>')


def not_exists(path, name):
    """Passes only when `path` does NOT exist in the JSON answer (e.g. there is no 6th order)."""
    return (f'<JSONPathAssertion guiclass="JSONPathAssertionGui" testclass="JSONPathAssertion" testname="{escape(name)}" enabled="true">'
            f'<stringProp name="JSON_PATH">{escape(path)}</stringProp><stringProp name="EXPECTED_VALUE"></stringProp>'
            '<boolProp name="JSONVALIDATION">false</boolProp><boolProp name="EXPECT_NULL">false</boolProp>'
            '<boolProp name="INVERT">true</boolProp><boolProp name="ISREGEX">false</boolProp></JSONPathAssertion><hashTree/>')


def build(only=None) -> str:
    inst = "${INSTANCE}"
    sym = "${SYMBOL}"

    setup = controller("SETUP  log in (not a bug check)", cookies() + (
        sampler("login", "POST", "/api/auth/login", '{"email":"${EMAIL}","password":"${PASSWORD}"}', code_assert(200)) +
        sampler("chart-token", "POST", "/api/auth/chart-token", "", code_assert(200) + extractor("TOKEN", "$.token"))))

    auth = hdr([("Authorization", "Bearer ${TOKEN}"), ("X-Broker-ID", inst)])

    def bug_post(name, body, code=400, extra=""):
        return sampler(name, "POST", f"/v1/oms/{inst}/orders", body,
                       code_assert(code, f"EXPECTED HTTP {code}", ignore_status=True) + extra)

    bug1 = sampler("BUG-1  GET /orders?limit=5  (expected: at most 5 orders)", "GET", f"/v1/oms/{inst}/orders?limit=5", None,
                   code_assert(200, "HTTP 200", ignore_status=True) + not_exists("$.orders[5]", "EXPECTED at most 5 orders (no 6th order)"))
    bug2 = bug_post("BUG-2  POST /orders type=WEIRD  (expected: HTTP 400)",
                    '{"symbol":"' + sym + '","side":"BUY","type":"WEIRD","qty":1}')
    bug3 = bug_post("BUG-3  POST /orders tp=-1 sl=1e30  (expected: HTTP 400, no trade)",
                    '{"symbol":"' + sym + '","side":"BUY","type":"MARKET","qty":0.01,"tp":-1,"sl":1e30}',
                    extra=extractor("MID_BUG3", "$.order.market_order_id"))
    control = bug_post("CONTROL  POST /orders side=HOLD  (a normal HTTP 400 - works)",
                       '{"symbol":"' + sym + '","side":"HOLD","type":"MARKET","qty":1}')
    cleanup = sampler("CLEANUP  close the trade BUG-3 wrongly opened", "POST", f"/v1/oms/{inst}/positions/${{MID_BUG3}}/squareoff", "{}",
                      code_assert(200, "ignore", ignore_status=True))

    if only == 3:
        checks = controller("BUG-3 CHECK  (red = bug present)", auth + bug3 + cleanup)
    elif only == 2:
        checks = controller("BUG-2 CHECK  (red = bug present)", auth + bug2 + control)
    elif only == 1:
        checks = controller("BUG-1 CHECK  (red = bug present)", auth + bug1)
    else:
        checks = controller("BUG CHECKS  (red = bug present)", auth + bug1 + bug2 + bug3 + control + cleanup)

    TG_NAME = f'BUG-{only} only (1 user, 1 run)' if only else 'Show the 3 bugs (1 user, 1 run)'
    tg = (f'<ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="{TG_NAME}" enabled="true">'
          '<stringProp name="ThreadGroup.on_sample_error">continue</stringProp>'
          '<elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" '
          'testname="Loop Controller" enabled="true"><boolProp name="LoopController.continue_forever">false</boolProp>'
          '<stringProp name="LoopController.loops">1</stringProp></elementProp>'
          '<stringProp name="ThreadGroup.num_threads">1</stringProp><stringProp name="ThreadGroup.ramp_time">1</stringProp>'
          '<boolProp name="ThreadGroup.scheduler">false</boolProp><stringProp name="ThreadGroup.duration"></stringProp>'
          '<stringProp name="ThreadGroup.delay"></stringProp><boolProp name="ThreadGroup.same_user_on_next_iteration">false</boolProp>'
          f'</ThreadGroup><hashTree>{setup}{checks}</hashTree>')

    variables = [("HOST", P("HOST", "lpadmin.blackfx.com")), ("PORT", P("PORT", 443)), ("PROTOCOL", P("PROTOCOL", "https")),
                 ("INSTANCE", P("INSTANCE", "paper")), ("SYMBOL", P("SYMBOL", "BINANCE:BTCUSDT.P")),
                 ("EMAIL", P("EMAIL", "follower1@mailinator.com")), ("PASSWORD", P("PASSWORD", "CHANGE_ME"))]
    udv = "".join(
        f'<elementProp name="{k}" elementType="Argument"><stringProp name="Argument.name">{k}</stringProp>'
        f'<stringProp name="Argument.value">{escape(v)}</stringProp><stringProp name="Argument.metadata">=</stringProp></elementProp>'
        for k, v in variables)
    defaults = ('<ConfigTestElement guiclass="HttpDefaultsGui" testclass="ConfigTestElement" testname="HTTP Request Defaults" enabled="true">'
                '<elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" '
                'testname="User Defined Variables" enabled="true"><collectionProp name="Arguments.arguments"/></elementProp>'
                '<stringProp name="HTTPSampler.domain">${HOST}</stringProp><stringProp name="HTTPSampler.port">${PORT}</stringProp>'
                '<stringProp name="HTTPSampler.protocol">${PROTOCOL}</stringProp><stringProp name="HTTPSampler.contentEncoding">UTF-8</stringProp>'
                '<stringProp name="HTTPSampler.path"></stringProp><stringProp name="HTTPSampler.connect_timeout">8000</stringProp>'
                '<stringProp name="HTTPSampler.response_timeout">60000</stringProp></ConfigTestElement><hashTree/>')
    plan_hdr = hdr([("Content-Type", "application/json"), ("Accept", "application/json")])

    return ('<?xml version="1.0" encoding="UTF-8"?>\n<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3"><hashTree>'
            '<TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="BlackTrader - the 3 bugs" enabled="true">'
            '<stringProp name="TestPlan.comments">Red = bug present. Set EMAIL / PASSWORD below (TEST account, paper). Generated by tests/jmeter/build_bug_plan.py</stringProp>'
            '<boolProp name="TestPlan.functional_mode">true</boolProp><boolProp name="TestPlan.tearDown_on_shutdown">true</boolProp>'
            '<boolProp name="TestPlan.serialize_threadgroups">true</boolProp>'
            '<elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" '
            f'testname="User Defined Variables" enabled="true"><collectionProp name="Arguments.arguments">{udv}</collectionProp></elementProp>'
            '<stringProp name="TestPlan.user_define_classpath"></stringProp></TestPlan><hashTree>'
            + plan_hdr + defaults + tg + listener("tree", "View Results Tree") + listener("summary", "Summary Report") +
            '</hashTree></hashTree></jmeterTestPlan>\n')


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print("wrote", OUT)
    for n in (1, 2, 3):
        o = OUT.with_name(f"blacktrader_bug{n}_only.jmx")
        o.write_text(build(only=n), encoding="utf-8")
        print("wrote", o)
