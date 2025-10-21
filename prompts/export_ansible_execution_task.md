Process ALL migration checklist items for module: {module}

CHEF SOURCE PATH: {chef_path}
ANSIBLE OUTPUT PATH: {ansible_path}

MIGRATION PLAN FOR REFERENCE:
{migration_plan}

CHECKLIST TO PROCESS:
<document>
{checklist}
</document>

CRITICAL INSTRUCTIONS:
You MUST process EVERY SINGLE ITEM in the checklist that is marked as "pending", "missing", or "error".

Your task:
1. Go through the ENTIRE checklist from top to bottom
2. For EACH item that needs processing:
   a. Read the Chef source file (if it exists, skip if "N/A")
   b. Convert it to the appropriate Ansible format
   c. Write it to the target Ansible location using the correct tool
   d. Use the ansible_lint tool to validate every single generated file individually
   e. Fix all found errors and revalidate the file using the ansible_lint
   f. Keep repeating fixing issues and revalidating until the validation passes. You CAN NOT move to next item until the current one is correct.
   g. Use update_checklist_task to mark the item as "complete" with notes about what was done
3. Do NOT stop after creating just one or a few files, you MUST repeat the loop for all checklist items
4. Process ALL items before finishing

IMPORTANT: After successfully creating each file, you MUST call:
update_checklist_task(source_path, target_path, status="complete", notes="Description of what was created")

**CRITICAL PATH FORMAT**: Use EXACT paths from the checklist (as shown in the checklist document above).
When calling update_checklist_task, you MUST use the paths EXACTLY as they appear in the checklist:
- source_path: Copy the exact source path from the checklist (full path including cookbooks prefix)
- target_path: Copy the exact target path from the checklist (full path including ansible/{module} prefix)
- DO NOT modify, shorten, or add prefixes - use paths EXACTLY as shown in the checklist

Example: If checklist shows "cookbooks/myapp/templates/default/config.erb → ansible/myapp/templates/config.j2"
- source_path = "cookbooks/myapp/templates/default/config.erb"
- target_path = "ansible/myapp/templates/config.j2"

Suggested order for the task:
- Process structure files first (meta/main.yml, handlers/main.yml)
- Then attributes/variables (defaults/main.yml)
- Static files (copy using copy_file tool)
- Templates (convert ERB to Jinja2)
- ALL recipe/task files (CRITICAL: see validation workflow below)

VALIDATION WORKFLOW FOR TASK FILES:
After writing EACH task file (tasks/*.yml):
1. Run ansible_role_check on the role directory
2. If validation fails with syntax errors, read the task file you just wrote
3. Fix the errors immediately (for example remove 'hosts:', 'tasks:' wrapper, fix deprecated syntax)
4. Write the fixed file using the ansible_write tool
5. Make sure the ansible_lint passes on the fixed file
6. Run the ansible_role_check tool again to confirm the fix
7. Keep fixing if an error is found - make sure both the ansible_lint and ansible_role_check pass on the task file
8. Only then move to the next file

For each file you complete, state: "COMPLETED: source → target"
For any errors, state: "ERROR: source → target - reason"

YOU MUST WORK THROUGH THE COMPLETE CHECKLIST. Do not stop early.
