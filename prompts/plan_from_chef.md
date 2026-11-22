## Chef-to-Ansible Planning Rules

- Use the migration plan's defaults/main.yml and vars/main.yml attribute groups. For older plans without groups, read all contributing attribute files and map default/force_default to defaults and normal/override/force_override to vars; classify assignments, not filenames.
- Keep each grouped dictionary intact. A dictionary with higher-level values belongs wholly in vars, including inherited keys.
- Add one task per variable target across all categories. Treat existing entries for that target as covered regardless of source; do not add separate structure tasks.
- Use one representative source_path. In each target's description, list every contributing source file and every resolved assignment as `attribute_path = effective_value`. Include only assignments belonging to that target.
- Include plain data bags in the same vars/main.yml task, preserving bag/item IDs.
