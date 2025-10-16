Validate the migration for module: {module}

CHEF SOURCE PATH: {chef_path}
ANSIBLE OUTPUT PATH: {ansible_path}

MIGRATION PLAN:
{migration_plan}

CURRENT CHECKLIST STATE:
{checklist}

CHEF FILES AVAILABLE:
{chef_files}

ANSIBLE FILES GENERATED:
{ansible_files}

CRITICAL: You must ACTUALLY CHECK if files exist and validate their content. Do not assume or hallucinate.

NOTE: ansible_role_check has ALREADY been run successfully. The role passes Ansible's syntax validation.

Your validation tasks:

1. RUN ANSIBLE-LINT
   - Use the ansible_lint tool to check for syntax and best practices
   - If this reports errors, the migration has FAILED

2. CHECK FILE EXISTENCE - USE list_directory TOOL
   For EACH item in the checklist:
   - Use list_directory to verify the target file exists
   - If the file is NOT in the ANSIBLE FILES GENERATED list above, it is MISSING
   - Mark as "missing" if file does not exist

3. VALIDATE CONTENT (only for files that exist)
   For files that exist:
   - Use read_file to read the Ansible file
   - Compare with the Chef source (if applicable) using diff_file
   - Check for correct conversion (ERB→Jinja2, Chef resources→Ansible tasks, etc.)
   - Verify completeness

4. UPDATE CHECKLIST STATUS - USE THE TOOLS
   For each item in the checklist, use the update_checklist_task tool to update its status:

   TOOL: update_checklist_task(source_path, target_path, status, notes)

   Determine the REAL status by checking the ANSIBLE FILES GENERATED list:
   - status="complete" ONLY if file exists in the list AND content is correct
   - status="missing" if the target file is NOT in the ANSIBLE FILES GENERATED list
   - status="error" if file exists but has problems (include specific error details in notes)

   IMPORTANT: Cross-reference each checklist item's target path with the ANSIBLE FILES GENERATED list.
   If a file is not in that list, it is MISSING. Do not mark it as complete.

   Use the exact source_path and target_path from the checklist. Valid status values: "complete", "pending", "missing", "error"

5. CHECK PROGRESS
   After updating all tasks, use get_checklist_summary to verify the overall status.

Output your validation findings:

## Validation Report: {module}

### Overall Status
(Use get_checklist_summary to report completion percentage and statistics)

### Issues Found
(List any critical problems discovered during validation, with file paths and specific errors)

### Next Steps
(If incomplete, briefly describe what needs to be fixed)

BE ACCURATE. Only mark files as complete if they actually exist in the ANSIBLE FILES GENERATED list.
