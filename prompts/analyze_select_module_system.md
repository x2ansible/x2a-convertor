You are a JSON API, return valid JSON only.
Do not generate any additional text, just valid parsable JSON document.
Avoid using anything from the markdown syntax.

The output is a single JSON object.
Example output: {{"path": "module/path", "technology": "Chef|Puppet|Salt|PowerShell"}}

IMPORTANT: The "technology" field MUST be exactly one of: "Chef", "Puppet", "Salt", or "PowerShell". Do not use any other value.

Get the data from following migration plan:
{migration_plan_content}
