Analyze this directory for migration to Ansible.

User requirements: {user_requirements}

Use `list_directory` and `file_search` to explore the repository structure. Do not assume any structure, discover it by navigating the directory tree, current list directory is:

```
{files}
```

Based on your findings, create a comprehensive `{migration_plan_file}` file that follows the template structure.

Focus on:
1. Identifying the current technology (Chef, Puppet, Salt, PowerShell, etc.) from file extensions and structure (.rb for Chef, .ps1/.psm1/.psd1 for PowerShell, .pp for Puppet, .sls for Salt)
2. Cataloging all modules/cookbooks/manifests and their purposes
3. Mapping dependencies (Berksfile, Policyfile, metadata, etc.)
4. Identifying configuration files, secrets, and security considerations
5. Estimating migration complexity and timeline based on module count
6. Providing coordination guidance for teams

Write the complete migration plan to `{migration_plan_file}` in the root directory.
