**Analyze the Chef cookbook at path: {path}**
**User requirements: {user_message}**

**Directory listing for {path}:**
```
{directory_listing}
```

**Tree-sitter structural analysis:**
{tree_sitter_report}

**INSTRUCTIONS:**
1. Use the `read_file` tool to examine all files like `metadata.rb`, `recipes/*.rb`, `attributes/*.rb`, templates, etc.
2. Use the `file_search` tool to find specific patterns if needed  
3. Use the `list_directory` tool if you need to explore subdirectories
4. Analyze the complete cookbook workflow and dependencies
5. Provide your final response as a detailed text migration plan (NOT as a tool call)

Follow the MANDATORY ANALYSIS STEPS from the system prompt and write the migration plan using the template format provided in the system prompt.
