;;; d46_anchor_capture.lsp — Phase D4.6.2 AutoCAD Anchor Capture Command
;;; Usage: D46ANCHOR
;;; Prompts user to click 3 reference/sandbox anchor pairs, writes JSON.
;;; NO drawing, NO save, NO command execution.

(defun c:D46ANCHOR ( / f p1_ref p1_sbx p2_ref p2_sbx p3_ref p3_sbx pt_ref pt_sbx)
  (princ "\n=== D4.6 Anchor Capture — 3-point calibration ===\n")
  (princ "Switch to reference DWG tab and click point #1, then sandbox.\n")

  (setq p1_ref (getpoint "\nReference point 1: "))
  (setq p1_sbx (getpoint "\nSandbox point 1: "))

  (setq p2_ref (getpoint "\nReference point 2: "))
  (setq p2_sbx (getpoint "\nSandbox point 2: "))

  (setq p3_ref (getpoint "\nReference point 3: "))
  (setq p3_sbx (getpoint "\nSandbox point 3: "))

  (setq f (open "D:/ExampleWorkspace/天正/artifacts/alignment/anchors_d4_6.json" "w"))
  (write-line "{" f)
  (write-line "  \"phase\": \"D4.6.2\"," f)
  (write-line "  \"anchor_count\": 3," f)
  (write-line "  \"reference_anchor_points\": [" f)
  (write-line (strcat "    [" (rtos (car p1_ref) 2 1) ", " (rtos (cadr p1_ref) 2 1) ", 0],") f)
  (write-line (strcat "    [" (rtos (car p2_ref) 2 1) ", " (rtos (cadr p2_ref) 2 1) ", 0],") f)
  (write-line (strcat "    [" (rtos (car p3_ref) 2 1) ", " (rtos (cadr p3_ref) 2 1) ", 0]") f)
  (write-line "  ]," f)
  (write-line "  \"sandbox_anchor_points\": [" f)
  (write-line (strcat "    [" (rtos (car p1_sbx) 2 1) ", " (rtos (cadr p1_sbx) 2 1) ", 0],") f)
  (write-line (strcat "    [" (rtos (car p2_sbx) 2 1) ", " (rtos (cadr p2_sbx) 2 1) ", 0],") f)
  (write-line (strcat "    [" (rtos (car p3_sbx) 2 1) ", " (rtos (cadr p3_sbx) 2 1) ", 0]") f)
  (write-line "  ]," f)
  (write-line "  \"source_dwg_opened\": false," f)
  (write-line "  \"source_dwg_saved\": false," f)
  (write-line "  \"sendcommand_used\": false," f)
  (write-line "  \"tianzheng_command_executed\": false," f)
  (write-line "  \"production_d1_allowed\": false" f)
  (write-line "}" f)
  (close f)
  (princ "\nAnchors written to artifacts/alignment/anchors_d4_6.json\n")
  (princ "Return to Codex to continue calibration.\n")
  (princ)
)
(princ "\nD46ANCHOR command loaded. Type D46ANCHOR to start.\n")
(princ)
