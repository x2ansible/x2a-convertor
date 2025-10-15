# Validate Migration: {module}

## Migration Plan

{migration_plan_content}

## Chef Source Files
Location: `{chef_path}`

Files found:
```
{chef_files}
```

## Current Ansible Output
Location: `{ansible_path}`

Files currently present:
```
{ansible_files}
```

## Your Task

Validate that EVERY Chef file listed above has been properly converted to Ansible. Fix any missing or incomplete conversions.

### Step-by-Step Process

1. **Identify what needs to be converted** - Look at the Chef files list above
   - Count recipes (recipes/*.rb)
   - Count templates (templates/default/*.erb)
   - Count static files (files/default/*)
   - Count attributes (attributes/*.rb)

2. **For EACH Chef file, check its Ansible equivalent:**

   **For each template file (templates/default/*.erb):**
   - Use `diff_file` to compare Chef .erb with Ansible .j2
   - If diff shows proper conversion → Mark as COMPLETE, move to next file
   - If .j2 is missing or diff shows stub content (`{{ placeholder }}`) → Read .erb, convert to Jinja2, write with `write_file`

   **For each recipe file (recipes/*.rb):**
   - Check if corresponding tasks/*.yml exists
   - If exists and has real Ansible tasks → Mark as COMPLETE, move to next file
   - If missing or incomplete → Read the .rb, convert to Ansible tasks, write with `ansible_write`

   **For each static file (files/default/*):**
   - Check if corresponding files/* exists
   - If exists → Mark as COMPLETE, move to next file
   - If missing → Use `copy_file` to copy it

   **For attributes/default.rb:**
   - Check if defaults/main.yml exists and has all variables
   - If complete → Mark as COMPLETE
   - If missing or incomplete → Read attributes, convert to YAML, write with `ansible_write`

3. **After checking/fixing ALL files, produce your validation report**
   - List every Chef file and its status
   - Mark `[x]` for complete conversions
   - Mark `[ ]` for missing conversions
   - Calculate completion percentage
   - Set STATUS: COMPLETE or STATUS: INCOMPLETE

### Expected Conversions

Based on the migration plan, you should create:

- One task file (tasks/*.yml) for EACH recipe file (recipes/*.rb)
- One Jinja2 template (templates/*.j2) for EACH ERB template (templates/default/*.erb)
- One defaults/main.yml with ALL variables from attributes/*.rb
- Copied static files in files/* for EACH file in files/default/*
- Structure files: main.yml, tasks/main.yml, handlers/main.yml

### Common Issues to Fix

- **Stub templates**: Files containing only `{{ variable }}` placeholders instead of full converted content
- **Missing templates**: Templates listed in migration plan but not created in templates/ directory
- **Incomplete task files**: Missing tasks for Chef resources like directory creation, file copying
- **Missing handlers**: Services that need restart handlers
- **Missing static files**: HTML, config files that should be copied

### Final Output

Produce exactly ONE validation {ansible_path}/validation-report.md report file following the format stated in the system prompt.
Do not produce multiple reports or keep repeating the same actions.
