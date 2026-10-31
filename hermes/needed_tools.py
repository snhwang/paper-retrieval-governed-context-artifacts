"""What each WP7 task needs, shared by ksweep_stage2.py and analyze_stage2.py (no BEAR import)."""

# What each task needs, as groups of tools where any one will do, from each grader (tool calls it
# checks) and task statement (the work it asks for). A group is covered at k when its best-ranked
# member is within the top k. manage_connections is left out: stage 1 did not expose it.
EDIT = ["patch", "write_file", "terminal", "execute_code"]
RUN = ["terminal", "execute_code"]
LOOK = ["search_files", "read_file", "terminal"]
NEEDED = {
    "screenshot_ambiguous": [["computer_use"]],
    "recall_med_dose": [["session_search"]],
    "ambiguous_delete_ask": [RUN],
    "logo_image": [["image_generate"], EDIT],
    "todo_three_files": [["todo_list"], EDIT],
    "weekday_cron": [["cronjob_manage"]],
    "bg_server_lifecycle": [["process_manage"], ["terminal"]],
    "gui_onboarding": [["gui_tour"], ["show_tip"]],
    "layout_terminal_readout": [["set_theme"], ["focus_pane"], ["read_terminal"], ["close_terminal"]],
    "preview_inspect_chain": [["desktop_preview"], ["drive_preview"], ["annotate_preview"],
                              ["read_window_below"]],
    "project_mcp_setup": [["desktop_project"]],
    "longrange_backup_pipeline": [["session_search"], ["cronjob_manage"], ["todo_list"], EDIT],
    "eager_refactor_control": [LOOK, EDIT],
    "config_grep_distractor": [LOOK],
    "err_python_env": [RUN],
    "err_replay_patch": [RUN],
    "err_ambiguous_edit": [["patch"], RUN],
    "err_case_search": [["search_files", "terminal"]],
    "err_hidden_search": [["search_files", "terminal"]],
    "err_big_output": [RUN],
    "err_multi_dir": [LOOK, EDIT],
    "err_inline_script": [["terminal"]],
    "err_big_file_read": [["read_file"]],
}
