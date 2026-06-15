Analyze the following migration plan and extract metadata for all modules/cookbooks identified.

Look for sections like "MODULE INVENTORY" or similar that list the distinct modules in the repository.

## Example Input (abbreviated):

```
### MODULE INVENTORY
- **application_server**
  - **Description**: Deploys application runtime, configures service, and manages dependencies
  - **Path**: `cookbooks/application_server`
  - **Technology**: Chef

- **load_balancer**
  - **Description**: Configures load balancer with backend pools and health checks
  - **Path**: `cookbooks/load_balancer`
  - **Technology**: Chef
```

## Expected Output for Above Example:

Return a collection with two modules:
1. Module with name="application_server", path="cookbooks/application_server", description="Deploys application runtime, configures service, and manages dependencies.", technology="Chef"
2. Module with name="load_balancer", path="cookbooks/load_balancer", description="Configures load balancer with backend pools and health checks.", technology="Chef"

---

## Now extract from this migration plan:

<migration_plan>
{migration_plan_content}
</migration_plan>

Extract the following for each module:
1. **name**: The module or cookbook name (string)
2. **path**: Relative path to the module directory (string)
3. **description**: Brief description of what this module does, 1-2 sentences maximum (string)
4. **technology**: Source technology - must be exactly one of: "Chef", "Puppet", "Salt", "PowerShell", or "Ansible" (enum value)

Focus on distinct modules/cookbooks/roles only. Do not extract individual recipes, templates, or infrastructure files.
