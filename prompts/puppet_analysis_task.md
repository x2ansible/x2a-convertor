**Analyze the Puppet module at path: {path}**
**User requirements: {user_message}**

# CRITICAL: EXECUTION TREE (USE THIS AS YOUR SOURCE OF TRUTH)

The following execution tree shows the COMPLETE class execution flow.
You MUST use this data. Do NOT hallucinate or invent files that aren't listed here.

```
{execution_tree}
```

# EXTERNAL DEPENDENCIES (Puppetfile)

```
{dependencies_summary}
```

# CUSTOM TYPES AND PROVIDERS

```
{custom_types_summary}
```

# PUPPETDB USAGE

```
{puppetdb_summary}
```

# CREDENTIALS SUMMARY

```
{credentials_summary}
```

**VALIDATION RULES:**
- **File Structure**: List ONLY files shown in the execution tree and directory listing
- **Module Explanation**: Follow the execution tree order exactly
- **Iterations**: The execution tree shows loops with all items listed - copy those exact names
- **Variables**: Use the `parse_hiera_config` tool to understand the Hiera hierarchy, then read data files to map variables
- **Credentials**: Use the credentials summary for the Credentials section
- **PuppetDB**: Use the PuppetDB usage summary for the PuppetDB Dependencies section — include all exported resources, collectors, and queries
- **DO NOT invent anything**: If it's not in the execution tree, don't include it

---

**Directory listing for {path}:**
```
{directory_listing}
```

**Tree-sitter structural analysis:**
{tree_sitter_report}

**INSTRUCTIONS:**
1. **PRIMARY SOURCE**: Use the structured analysis data above - it contains the complete execution flow
2. Use the `parse_hiera_config` tool to discover the Hiera hierarchy and data files
3. Use the `read_file` tool to read Hiera data files and any file content not in the structured analysis
4. Use the `file_search` tool to find specific patterns if needed
5. Use the `list_directory` tool if you need to explore subdirectories
6. **CRITICAL**: Cross-check your migration plan against the structured analysis - every file you mention MUST be in the analysis
7. **FILE PATHS**: When listing files, use the EXACT paths from the directory listing
8. Provide your final response as a detailed text migration plan (NOT as a tool call)

Follow the MANDATORY ANALYSIS STEPS from the system prompt and write the migration plan using the template format provided in the system prompt.
