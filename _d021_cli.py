# -*- coding: utf-8 -*-
"""D0.2.1 fix: update manual_command_recording.py CLI --before support."""
import os

BASE = r"C:\Users\example-user\.agents\skills\autocad-dwg-redraw-skill-main\autocad-dwg-redraw-skill-main\skills\autocad-dwg-redraw"
SCR = os.path.join(BASE, "scripts", "tianzheng")

path = os.path.join(SCR, "manual_command_recording.py")
with open(path, "r", encoding="utf-8-sig") as f:
    content = f.read()

# Add --before argument
old = 'parser.add_argument("--wait", type=int, default=0)'
new = 'parser.add_argument("--before", default=None, help="Before recording JSON (stage=after)")\n    parser.add_argument("--wait", type=int, default=0)'
content = content.replace(old, new)

# Update after stage to handle --before
old_after = '''    elif args.stage == "after":
        print("\\nCapturing AFTER user action..."); rec = capture_after(acad); _pr(rec)
        data = {"stage":"after","recording":rec.to_dict(),"environment":env}'''

new_after = '''    elif args.stage == "after":
        print("\\nCapturing AFTER user action...")
        rec = capture_after(acad)
        _pr(rec)
        if args.before:
            from scripts.tianzheng.manual_command_recorder import load_before_json, generate_enhanced_diff
            before_data = load_before_json(args.before)
            pair = generate_enhanced_diff(before_data, rec)
            data = {"stage":"after","pair":pair,"environment":env}
        else:
            data = {"stage":"after","recording":rec.to_dict(),"environment":env}'''

content = content.replace(old_after, new_after)

# Update report generation for after stage
old_report = '''    if args.report:
        if args.stage == "both":
            report = generate_manual_recording_report(pair.to_dict(), env)
        else:
            sp = {"before":rec.to_dict() if args.stage == "before" else {}, "after":rec.to_dict() if args.stage == "after" else {}}
            report = generate_manual_recording_report(sp, env)'''

new_report = '''    if args.report:
        if args.stage == "both":
            report = generate_manual_recording_report(pair.to_dict(), env)
        elif args.stage == "after" and args.before:
            from scripts.tianzheng.macro_report import generate_enhanced_recording_report
            report = generate_enhanced_recording_report(data.get("pair",{}), env)
        else:
            sp = {"before":rec.to_dict() if args.stage == "before" else {}, "after":rec.to_dict() if args.stage == "after" else {}}
            report = generate_manual_recording_report(sp, env)'''

if old_report in content:
    content = content.replace(old_report, new_report)
    print("Report section updated")
else:
    print("Report section not found - may need manual fix")

# Write back WITHOUT BOM
with open(path, "w", encoding="utf-8", newline="") as f:
    f.write(content)
print("manual_command_recording.py updated with --before support")
