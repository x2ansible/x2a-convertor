Create a migration checklist for the module: {module}

MIGRATION PLAN:
{module_migration_plan}

CHEF DIRECTORY LISTING:
{directory_listing}

CHEF SOURCE PATH: {path}
ANSIBLE OUTPUT PATH: ./ansible/{module}

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

Examples:
- add_checklist_task(category="templates", source_path="templates/default/nginx.conf.erb", target_path="templates/nginx.conf.j2", description="Nginx configuration template")
- add_checklist_task(category="recipes", source_path="recipes/default.rb", target_path="tasks/main.yml", description="Main recipe tasks")
- add_checklist_task(category="structure", source_path="N/A", target_path="meta/main.yml", description="Role metadata")

Make sure to add EVERY file mentioned in the migration plan. Be complete and thorough.

After adding all tasks, use get_checklist_summary to confirm the checklist is complete.
