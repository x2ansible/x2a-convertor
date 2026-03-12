**TASK: Clean and format the migration plan**

**Messy Migration Plan Input:**
```
{messy_specification}
```

**Instructions:**

1. **Remove ALL artifacts** - Strip out any JSON tool calls or similar artifacts
2. **Extract real content** - Find actual migration plan improvements buried in the validation updates
3. **Consolidate duplicates** - Remove repetitive information and merge similar sections
4. **Apply proper formatting** - Follow the migration plan template structure exactly
5. **Preserve accuracy** - Keep all validated factual information (operations, paths, modules, modernization mappings)

**Key Requirements:**
- Every legacy pattern must be mapped to its modern equivalent
- All task/handler files must be mentioned in correct execution order
- All loops must be documented with their modernization approach
- Module parameter drift must be flagged where applicable
- Collection dependencies must be complete
- Template modernization needs must be documented
- Argument specification variables must be listed
- Pre-flight checks must exist for every managed service

**Output:** Provide ONLY the cleaned, final migration plan following the proper template format. No explanations or commentary.
