## Chef-to-Ansible Migration Rules

### ATTRIBUTES (attributes/*.rb → Ansible variables)
- Use the migration plan's attribute target groups and effective cookbook values as authoritative. Source assignments explain provenance only; do not re-merge source writes, regroup by filename, or restore overwritten values.
- Define each Ansible variable in one target only. If a dictionary contains values from both groups, write its complete effective value to `vars/main.yml`, including inherited keys. Ansible does not recursively merge role defaults with role vars.
- For older plans without target groups, read all contributing files and map default/force_default to defaults and normal/override/force_override to vars. Classify assignments, not filenames.

### WRITING VARIABLE TARGETS
For Chef defaults/main.yml and vars/main.yml, collect all entries with the same target_path,
including structure, attributes, and data bag entries. Read their descriptions and contributing
sources together. Produce one complete file for that target, preserving contributions from
completed entries. Write it once for the group, then mark every pending/missing entry in that
group complete using its exact source_path and target_path. If all entries are complete, skip it.

### DATA BAGS (data_bags/**/*.json → vars/main.yml):
- Read every plain data bag item listed in the migration plan when writing vars/main.yml, even when the checklist has one representative source path
- Preserve each plain data bag item as a structured variable, grouped by data bag and item ID
- Use the exact item values from the migration plan; do not invent replacements
- Do not treat a data bag as a credential merely because it uses Chef data bags
- Replace encrypted data bag values with the provided AAP credential variables; never copy encrypted ciphertext into generated role files
