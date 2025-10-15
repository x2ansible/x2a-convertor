Process ALL migration checklist items for module: {module}

CHEF SOURCE PATH: {chef_path}
ANSIBLE OUTPUT PATH: {ansible_path}

MIGRATION PLAN FOR REFERENCE:
{migration_plan}

CHECKLIST TO PROCESS:
{checklist}

CRITICAL INSTRUCTIONS:
You MUST process EVERY SINGLE ITEM in the checklist that is marked as "pending", "missing", or "error".

Your task:
1. Go through the ENTIRE checklist from top to bottom
2. For EACH item that needs processing:
   a. Read the Chef source file (if it exists, skip if "N/A")
   b. Convert it to the appropriate Ansible format
   c. Write it to the target Ansible location using the correct tool
   d. Move on to the next item
3. Do NOT stop after creating just one or two files
4. Process ALL items before finishing

Suggested order:
- Structure files first (meta/main.yml, handlers/main.yml)
- Attributes/variables (defaults/main.yml)
- Static files (copy using copy_file tool)
- Templates (convert ERB to Jinja2)
- ALL recipe/task files (CRITICAL: see validation workflow below)

VALIDATION WORKFLOW FOR TASK FILES:
After writing EACH task file (tasks/*.yml):
1. Run ansible_role_check on the role directory
2. If validation fails with syntax errors, read the task file you just wrote
3. Fix the errors immediately (remove 'hosts:', 'tasks:' wrapper, fix deprecated syntax)
4. Run ansible_role_check again to confirm the fix
5. Only then move to the next file

For each file you complete, state: "COMPLETED: source → target"
For any errors, state: "ERROR: source → target - reason"

YOU MUST WORK THROUGH THE COMPLETE CHECKLIST. Do not stop early.
