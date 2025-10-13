# Export COMPLETE Ansible role based on the module migration plan
Follow ALL requirements stated in the system prompt.

## CRITICAL TASK
You must generate a COMPLETE, production-ready Ansible role by:
1. Using the module migration plan below as your PRIMARY SOURCE OF TRUTH
2. Creating ALL necessary Ansible files (playbook, tasks, templates, handlers, defaults, vars, files)
3. Converting Chef ERB templates to Jinja2 templates (read originals from "{path}" if needed for actual content)
4. Translating Chef resources described in the migration plan to equivalent Ansible modules
5. Writing a final migration report

It is CRITICAL that the generated Ansible code is semantically IDENTICAL to the Chef cookbook as described in the migration plan.
If the migration plan is unclear about any functionality, you MAY read the Chef source files from "{path}" using the read_file tool and document this in your report.

## User request
The user explicitly requests following:

{user_message}

### Directory listing for {path} path:
```
{directory_listing}
```

{previous_attempts}

## Module migration plan
The sources have been analyzed with following findings:

{module_migration_plan}

## High-level migration plan
If unclear, try to find answer in following high-level migration plan

{high_level_migration_plan}
