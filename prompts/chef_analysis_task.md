**Analyze the Chef cookbook at path: {path}**
**User requirements: {user_message}**

# CRITICAL: EXECUTION TREE (USE THIS AS YOUR SOURCE OF TRUTH)

The following execution tree shows the COMPLETE recipe execution flow.
You MUST use this data. Do NOT hallucinate or invent files that aren't listed here.

```
{execution_tree}
```

**VALIDATION RULES:**
- **File Structure**: List ONLY .rb files shown in the execution tree
- **Module Explanation**: Follow the execution tree order exactly - it shows the complete flow
- **Iterations**: The execution tree shows "LOOP over X" with all items listed - copy those exact names
- **Resources**: Use the [resource] entries shown in the tree
- **Custom Resources**: Use the [custom_resource] entries with provider paths shown
- **DO NOT invent anything**: If it's not in the execution tree, don't include it

**CRITICAL: ITERATION EXPANSION**
The execution tree shows loops like:
```
LOOP over collection_name (3 items)
├── item1 {{attribute: value}}
├── item2 {{attribute: value}}
└── item3 {{attribute: value}}
```

In your migration plan, you MUST list all items explicitly:
- "Iterations: Runs 3 times for: **item1**, **item2**, **item3**"
- Then describe each item with its attributes

NEVER WRITE: "For each item", "Configures multiple X", "Iterates over Y"
The tree already shows you the exact items - just copy them!

---

**Directory listing for {path}:**
```
{directory_listing}
```

**Tree-sitter structural analysis:**
{tree_sitter_report}

**INSTRUCTIONS:**
1. **PRIMARY SOURCE**: Use the structured analysis data above - it contains the complete execution flow
2. Use the `read_file` tool ONLY if you need to see specific file content not in the structured analysis
3. Use the `file_search` tool to find specific patterns if needed
4. Use the `list_directory` tool if you need to explore subdirectories
5. **CRITICAL**: Cross-check your migration plan against the structured analysis - every file you mention MUST be in the analysis
6. **FILE PATHS**: When listing files in your migration plan, use the EXACT paths from the directory listing above, including the `migration-dependencies/` prefix for dependency files
7. Provide your final response as a detailed text migration plan (NOT as a tool call)

Follow the MANDATORY ANALYSIS STEPS from the system prompt and write the migration plan using the template format provided in the system prompt.
