## Chef-to-Ansible Migration Rules

### ATTRIBUTES (attributes/*.rb → defaults/main.yml):
- Convert Ruby hash syntax to YAML
- default['key'] = 'value' becomes key: 'value'

### DATA BAGS (data_bags/**/*.json → vars/main.yml):
- Preserve each plain data bag item as a structured variable, grouped by data bag and item ID
- Use the exact item values from the migration plan; do not invent replacements
- Do not treat a data bag as a credential merely because it uses Chef data bags
- Replace encrypted data bag values with the provided AAP credential variables; never copy encrypted ciphertext into generated role files
