Create a migration checklist for the module: {module}

MIGRATION PLAN:
{module_migration_plan}

CHEF DIRECTORY LISTING:
```
{directory_listing}
```

CHEF SOURCE PATH: {path}
ANSIBLE OUTPUT PATH: ./ansible/{module}

<document>
{existing_checklist}
</document>

Read the migration plan carefully and create a complete checklist of all files that need to be migrated.

USE THE add_checklist_task TOOL to add each migration task:

TOOL: add_checklist_task(category, source_path, target_path, description)

Categories:
- "templates": ERB templates → Jinja2 templates
- "recipes": Chef recipes → Ansible tasks
- "attributes": Chef attributes → Ansible variables
- "files": Static files (configs, scripts, etc.)
- "structure": Generated Ansible role structure files (meta/main.yml, handlers/main.yml, etc.)

For each file in the migration plan:
1. Identify the category
2. Specify source_path (Chef file path, or "N/A" for generated files)
3. Specify target_path (Ansible file path)
4. Add optional description if helpful

**IMPORTANT**:
- source_path: Use EXACT full paths from the CHEF DIRECTORY LISTING above
- target_path: Use full path including ANSIBLE OUTPUT PATH (e.g., "ansible/{module}/templates/config.j2")

The directory listing shows full paths - you MUST use these complete paths for source_path.
For target_path, combine ANSIBLE OUTPUT PATH with the relative Ansible role path.

Examples:
- If directory listing shows "cookbooks/myapp/templates/default/config.erb", use that EXACT path as source_path
- For target_path, use the ANSIBLE OUTPUT PATH + relative role path (e.g., "ansible/myapp/templates/config.j2")
- For generated Ansible structure files, use source_path="N/A"

Sample calls (replace {module} with actual module name from ANSIBLE OUTPUT PATH):
- add_checklist_task(category="templates", source_path="<full_path_from_directory_listing>", target_path="ansible/{module}/templates/config.j2", description="Configuration template")
- add_checklist_task(category="recipes", source_path="<full_path_from_directory_listing>", target_path="ansible/{module}/tasks/main.yml", description="Main recipe tasks")
- add_checklist_task(category="structure", source_path="N/A", target_path="ansible/{module}/meta/main.yml", description="Role metadata")

Make sure to add EVERY file mentioned in the migration plan. Be complete and thorough.
