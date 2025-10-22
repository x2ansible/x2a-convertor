Validate the migration for module: {module}

CHEF SOURCE PATH: {chef_path}
ANSIBLE OUTPUT PATH: {ansible_path}

MIGRATION PLAN:
{migration_plan}

CURRENT CHECKLIST STATE:
<document>
{checklist}
</document>

Your steps of validation:
- For all checklist items listed above:
   - Use the read_file tool to read the Ansible file
   - Compare with the Chef source (if applicable) using diff_file
   - Check for correct conversion (ERB→Jinja2, Chef resources→Ansible tasks, etc.)
   - Verify completeness of the conversion
   - Update the checklist item using the update_checklist_task tool:
- When all checklist items are validated, produce your findings as a Validation Report 


When updating the checklist items via update_checklist_task(source_path, target_path, status, notes) tool, respect following rules:
  - status="complete" ONLY if target file content is correct
  - status="error" if the target file has problems (you MUST provide specific error details in notes)
  - Use the exact source_path and target_path from the checklist. Valid status values: "complete", "pending", "missing", "error"


When producing the Validation Report, use following structure:

## Validation Report: {module}

### Overall Status
(Use get_checklist_summary tool to report completion percentage and statistics)

### Issues Found
(List any critical problems discovered during validation, with file paths and specific errors)

### Next Steps
(If incomplete, briefly describe what needs to be fixed)

BE ACCURATE, do not hallucinate, state if you don't know.
