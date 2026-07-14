# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding="utf-8")

# Read the file to fix
target = r"scripts\tianzheng_water\water_command_variant_probe.py"
with open(target, "r", encoding="utf-8") as f:
    content = f.read()

# --- Fix 1: Remove duplicate dry_run / sent_to_autocad in to_dict() ---
to_dict_start = content.find('def to_dict(self)')
to_dict_end = content.find('class VariantProbeSession:', to_dict_start)
to_dict_block = content[to_dict_start:to_dict_end]

# Remove duplicate lines
lines = to_dict_block.split('\n')
fixed_lines = []
seen_dry_run = False
seen_sent = False
for line in lines:
    s = line.strip()
    if s == '"dry_run": self.dry_run,':
        if not seen_dry_run:
            fixed_lines.append(line)
            seen_dry_run = True
        # else skip duplicate
    elif s == '"sent_to_autocad": self.sent_to_autocad,':
        if not seen_sent:
            fixed_lines.append(line)
            seen_sent = True
        # else skip duplicate
    else:
        fixed_lines.append(line)

fixed_to_dict = '\n'.join(fixed_lines)
content = content[:to_dict_start] + fixed_to_dict + content[to_dict_end:]
print("Fix 1 (duplicate keys): done")

# --- Fix 2: Fix probe() indentation ---
# The indentation corruption: lines that should be indented more got dedented
# We need to fix from "if dry_run:" to end of probe method
probe_start = content.find('def probe(')
probe_lines = content[probe_start:].split('\n')

# Find the probe method end by looking for next top-level def/class after probe
# The corrupted sections have specific patterns
# Line after for loop needs +4 spaces
# session.results.append needs 16 spaces (4*4)
# .to_dict()) needs 16 spaces
# return session needs 12 spaces (after if block)

import re

# Actually, the simplest fix: rewrite the probe method body from scratch
# Find the end of probe method
probeline = content[probe_start:probe_start + content[probe_start:].find('\n')]
rest = content[probe_start:]
# Find next def/class at top level (0 indentation)
next_def = len(rest)
for m in re.finditer(r'^(def |class |# In)', rest, re.MULTILINE):
    if m.start() > len(probeline) + 1:
        next_def = m.start()
        break

probe_body = rest[:next_def]
probe_after = rest[next_def:]

print(f"Probe method length: {len(probe_body)} chars")
print("Fix 2: will rewrite probe method")

# Save intermediate
with open("_diagnostic.txt", "w", encoding="utf-8") as f:
    f.write(f"Probe method starts at offset {probe_start}\n")
    f.write(f"Probe method body chars: {len(probe_body)}\n")
    f.write(f"Next top-level after probe: {next_def}\n")
print("Diagnostics saved to _diagnostic.txt")
