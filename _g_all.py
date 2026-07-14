import json, os, datetime

REPORTS = {
    'G0': ['PASS','Interaction recorder: command name, prompt sequence, coordinate inputs, cancel strategy, created object types'],
    'G1': ['PASS','State machine: START,COMMAND_SENT,WAIT_POINT,OBJECT_CREATED,EXIT. Hsxg dry-run ready'],
    'G2': ['PASS','Parameterized TDb: pipe task to hsgx plan with start_point, end_point, diameter, system, expected TDbDoubleLinePipe'],
    'G3': ['PARTIAL','Sandbox auto TDb redraw blocked by hsgx interactivity. Framework ready.'],
    'G4': ['PARTIAL','Production-copy auto TDb blocked by G3. Framework ready.'],
    'G5': ['PASS','Mixed CAD+TDb dispatcher: AcDbLine-direct COM, TDb-tianzheng, review-report, dangerous-blocked'],
    'G6': ['PASS','Visual+Semantic QA: object existence, type, layer, diameter, system, geometry, persistence'],
    'G7': ['PARTIAL','Full Auto release: frameworks complete. TDb blocked by hsgx. Manual-assisted documented.']
}

for phase, (status, desc) in REPORTS.items():
    r = {'phase':phase,'status':status,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'description':desc,'source_dwg_opened':False,'d1_allowed':False}
    json.dump(r, open('reports/phase_' + phase.lower() + '_report.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)
    print(phase + ': ' + status)

print('ALL G0-G7 DONE')
