Analyze the following migration plan and extract metadata for all modules/cookbooks identified:

<migration_plan>
{migration_plan_content}
</migration_plan>

Extract the following for each module:
1. name: The module or cookbook name
2. path: Relative path to the module directory
3. description: Brief description of what this module does (1-2 sentences)
4. technology: Source technology (usually "Chef", but could be "Puppet" or "Salt")

Return a structured list of all modules found.
