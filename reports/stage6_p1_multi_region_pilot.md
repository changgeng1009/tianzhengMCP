> redacted / not_rerun: Historical artifact redacted for redistribution. Captured drawing geometry, native object properties, handles and input fingerprints are withheld. This cleanup did not connect to CAD or rerun/revalidate the original assertions. Historical outcomes are not current acceptance or synthetic-run evidence.

# Stage 6-P1 Rehearsal Stop Gate

- status: FAILED_REHEARSAL_STOP_GATE
- mapping revision: stage6_p1_user_final_mapping_20260712_r2
- matched regions: 7/7
- frozen plan SHA256: redacted_input_sha256
- planned/mapped/created: 4343/4343/4343
- existing modified: 6
- unexpected new: 33
- rehearsal saved/reopened: false/false
- original hashes unchanged: true
- original target write/save: false/false
- SendCommand/LISP/NETLOAD/Tianzheng command: false/false/false/false
- Production D1 allowed: false

## Stop Reason

RuntimeError: global pre-save QA failed: mapped=4343, modified_existing=6, unexpected=33

## Required Next Action

静态诊断 6 个 existing 变化与 33 个 unexpected 新对象的来源；修正克隆所有权/依赖映射后，必须由新的明确阶段授权才能从原始 target 的全新副本重新 rehearsal。

Input file fingerprints were redacted; historical checks were not rerun.
