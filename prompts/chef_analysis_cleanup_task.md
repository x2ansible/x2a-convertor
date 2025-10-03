**TASK: Clean and format the migration plan**

**Messy Migration Plan Input:**
```
{messy_specification}
```

**Instructions:**

1. **Remove ALL JSON artifacts** - Strip out any `{{"name": "file_search"...}}` or similar JSON tool calls
2. **Extract real content** - Find actual migration plan improvements buried in the validation updates
3. **Consolidate duplicates** - Remove repetitive information and merge similar sections
4. **Apply proper formatting** - Follow the migration plan template structure exactly
5. **Preserve accuracy** - Keep all validated factual information (instance names, ports, file paths, etc.)

**Key Requirements:**
- Every instance/site/database must be listed by exact name (no "for each")
- All recipes must be mentioned in correct execution order  
- All .each loops must be expanded with actual item names
- Pre-flight checks must exist for every named instance individually
- All package names must be real and verified
- Template rendering counts must be accurate

**Output:** Provide ONLY the cleaned, final migration plan following the proper template format. No explanations or commentary.
