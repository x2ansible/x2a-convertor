# Export Ansible playbook based on the Chef cookbook
Follow all requirements stated in the system prompt.

It is IMPORTANT that the generated the Ansible code is semantically as close as possible to the original Chef cookbooks.
So if you are still unclear about the requested functionality, use tools to collect the knowledge from sources which root is at the "{path}" path.

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

>>>>>>> Start of module migration plan
{module_migration_plan}
<<<<<<<  End of module migration plan

## High-level migration plan
If unclear, try to find answer in following high-level migration plan

>>>>>>> Start of high-level migration plan
{high_level_migration_plan}
<<<<<<<  End of high-level migration plan
