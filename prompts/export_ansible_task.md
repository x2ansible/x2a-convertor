# Export Ansible playbook based on Chef cookbook
Follow all requirements stated in the system prompt.

Store the exported Ansible playbook under {path}/ansible directory.

## User request
The user farther requests following:

{user_message}

{previous_attempts}

## Component migration plan
The sources have been analyzed with following findings:

>>>>>>> Start of component migration plan
{component_migration_plan}
<<<<<<<  End of component migration plan

## High-level migration plan
If unclear, try to find answer in following high-level migration plan

>>>>>>> Start of high-level migration plan
{high_level_migration_plan}
<<<<<<<  End of high-level migration plan

## Sources
It is important to generate the Ansible semantically as close as possible to the original Chef cookbooks. So if you are still unclear about the requested functionality, use tools to collect the knowledge from sources which root is at {path} path.

### Directory listing for {path} path:
```
{directory_listing}
```

## Output
Using the tools, especially `write_file`, write the generated Ansible content to the disk.

Provide report of your task as requested in the system prompt.