**Analyze the PowerShell code at path: {path}**
**User requirements: {user_message}**

# CRITICAL: ANALYSIS SUMMARY (USE THIS AS YOUR SOURCE OF TRUTH)

The following analysis summary shows the COMPLETE PowerShell execution flow.
You MUST use this data. Do NOT hallucinate or invent files that aren't listed here.

```
{execution_summary}
```

**VALIDATION RULES:**
- **File Structure**: List ONLY files shown in the analysis summary
- **Module Explanation**: Follow the analysis summary order exactly
- **Loops**: The analysis shows loop items - copy those exact names
- **Operations**: Use the operation entries shown in the summary
- **DO NOT invent anything**: If it's not in the analysis summary, don't include it

---

**Directory listing for {path}:**
```
{directory_listing}
```

**INSTRUCTIONS:**
1. **PRIMARY SOURCE**: Use the structured analysis data above
2. Use the `read_file` tool ONLY if you need to see specific file content not in the analysis
3. Use the `file_search` tool to find specific patterns if needed
4. Use the `list_directory` tool if you need to explore subdirectories
5. **CRITICAL**: Cross-check your migration plan against the analysis - every file you mention MUST be in the analysis
6. Provide your final response as a detailed text migration plan (NOT as a tool call)

Follow the MANDATORY ANALYSIS STEPS from the system prompt and write the migration plan using the template format provided.
