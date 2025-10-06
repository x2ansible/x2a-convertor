**TASK: Validate and improve migration plan based on file content**

**Current Migration Plan:**
```
{current_specification}
```

**File Being Analyzed:**
- **Path**: `{file_path}`
- **Content**:
```
{file_content}
```

**Instructions:**

1. Analyze this specific file content against the current migration plan
2. Check for:
   - Missing instances/sites/databases that should be listed by name
   - Unexpanded .each loops (expand them with actual names)
   - Missing pre-flight checks for discovered instances
   - Incorrect recipe execution order
   - Missing template rendering counts
   - Referenced files that don't exist
   - Invalid package names

3. Provide an updated section of the migration plan OR validation status

**Response Options:**
- **If updates needed**: Provide the corrected/expanded section of the migration plan
- **If validated**: "VALIDATED: [what was confirmed]"
- **If not relevant**: "SKIP: [reason]"

**Critical:** Expand ALL .each loops with actual item names. No "for each X" allowed.