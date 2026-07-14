
;;; Tianzheng Pipeline Loader — H1
;;; Load with: (load "tianzheng_pipeline_loader.lsp")
(if (findfile "tianzheng_pipeline_commands.lsp")
  (progn (load "tianzheng_pipeline_commands.lsp") (princ "\nPipeline commands loaded."))
  (princ "\nERROR: tianzheng_pipeline_commands.lsp not found"))
(princ)
