import zipfile, xml.etree.ElementTree as ET, json, re

with zipfile.ZipFile('MAM_Master_Test_Scenarios_Go_Live.docx') as z:
    xml_content = z.read('word/document.xml')
    tree = ET.fromstring(xml_content)
    
    rows = []
    for tr in tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tr'):
        cells = []
        for tc in tr.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tc'):
            cell_text = ''.join(tc.itertext()).strip()
            cells.append(cell_text)
        if cells and any('MAM-' in c for c in cells):
            rows.append(cells)

scenarios = []
for r in rows:
    tc_id = r[0].strip()
    scenario_pre = r[1].strip() if len(r) > 1 else ""
    steps_expected = r[2].strip() if len(r) > 2 else ""
    pri = r[3].strip() if len(r) > 3 else ""
    
    # parse scenario name and pre
    m_pre = re.split(r'Pre:\s*', scenario_pre, maxsplit=1)
    scenario_name = m_pre[0].strip()
    precondition = m_pre[1].strip() if len(m_pre) > 1 else ""
    
    # parse steps and expected
    m_exp = re.split(r'Expected:\s*', steps_expected, maxsplit=1)
    steps_text = m_exp[0].replace('Steps:', '').strip()
    expected_text = m_exp[1].strip() if len(m_exp) > 1 else ""
    
    # determine module
    prefix = tc_id.split('-')[1][0]
    module_map = {
        'F': 'Module 1: Group & Sub-Account Lifecycle',
        'A': 'Module 2: MAM Allocation Methods & Sizing Engine',
        'R': 'Module 3: Fractional Lot Rounding & Remainder Allocation',
        'E': 'Module 4: Order Execution, Modification & Bulk Routing',
        'P': 'Module 5: Partial Fills, Asymmetric Rejections & Slippage',
        'M': 'Module 6: Independent Sub-Account Margin, Leverage & Stop-Outs',
        'D': 'Module 7: Deposits, Withdrawals & Mid-Trade Disconnections',
        'H': 'Module 8: High-Water Mark & Performance Fees',
        'C': 'Module 9: Concurrency, Fan-Out & Race Conditions',
        'L': 'Module 10: Regulatory Compliance, LPOA & FIFO',
        'O': 'Module 11: Operational Tools & Emergency Runbooks'
    }
    
    scenarios.append({
        'id': tc_id,
        'module': module_map.get(prefix, 'Unknown Module'),
        'title': scenario_name,
        'precondition': precondition,
        'steps': steps_text,
        'expected': expected_text,
        'priority': pri
    })

print(f"Total structured scenarios parsed: {len(scenarios)}")
with open("scratch/all_165_scenarios.json", "w", encoding="utf-8") as f:
    json.dump(scenarios, f, indent=2)

# Count by module
from collections import Counter
counts = Counter(s['module'] for s in scenarios)
for mod, cnt in counts.items():
    print(f"  {mod}: {cnt}")

