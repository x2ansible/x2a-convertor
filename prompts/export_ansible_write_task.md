Write ALL files for module: {module}

CHEF SOURCE PATH: {chef_path}
ANSIBLE OUTPUT PATH: {ansible_path}

HIGH-LEVEL MIGRATION PLAN:
{high_level_migration_plan}

MODULE MIGRATION PLAN:
{migration_plan}

CHECKLIST:
<document>
{checklist}
</document>

Your task: Process ONLY items marked as "pending" or "missing". Skip items marked as "complete" - those files already exist.

Before writing each file, check if it already exists. If the target file exists, skip it and move to the next item.

## LINTING RULES

Your generated files will be validated with ansible-lint. Follow these rules to pass validation:

**FQCN (Fully Qualified Collection Names):**
- CORRECT: ansible.builtin.apt, ansible.builtin.service, ansible.builtin.template
- WRONG: apt, service, template
- For UFW: community.general.ufw (not just ufw)

**File paths:**
- Extract full paths from error messages (everything before first `:`)
- Example: `ansible/module/tasks/main.yml:7` → use `ansible/module/tasks/main.yml`

**No-changed-when:**
- Commands must have `changed_when` or `creates` parameter
- Example: command: echo test → Add: changed_when: false

**Arguments:**
- Remove invalid parameters for modules
- Example: file module doesn't accept `notify:` parameter

**File module for symlinks:**
- Use: state: link, src: /source, dest: /target
- Don't use: notify with file module

These rules prevent validation failures later.

Process order:
1. Structure files:
   - meta/main.yml: Read metadata.rb and convert to Ansible Galaxy format
   - handlers/main.yml: Create with common handlers (restart/reload services)
2. Attributes/variables (defaults/main.yml, vars/main.yml)
3. Static files (copy from files/)
4. Templates (convert .erb to .j2)
5. Recipes/tasks (convert .rb to .yml)

For each pending/missing item:
1. Check if target file exists - if yes, skip to next item
2. Read the Chef source file using read_file (skip if source is "N/A")
3. Convert to Ansible format following conversion rules
4. Write to target path using:
   - ansible_write for YAML files (tasks, handlers, defaults, vars, meta)
   - write_file for templates (.j2) and other files
   - copy_file for static files
5. IF ansible_write returns ERROR:
   - Read the error (has line number and problematic content)
   - Fix the specific YAML issue
   - Call ansible_write AGAIN with corrected content
   - DO NOT use write_file as fallback
6. Update checklist using update_checklist_task with:
   - source_path: EXACT path from checklist
   - target_path: EXACT path from checklist
   - status: "complete"
   - notes: Brief description of what was created

Continue until ALL pending/missing items are complete.

OPTIONAL: After all files are written, you can run ansible_lint on the output directory to catch any syntax issues early.

Report format:
For each completed file: "COMPLETED: source → target"
For each skipped file: "SKIPPED: source → target (already exists)"
For any issues: "ISSUE: source → target - reason"
