**Analyze the Puppet module at path: {path}**
**User requirements: {user_message}**

---

# YOUR DATA SOURCES

You have everything you need below. Do NOT read manifest files - the execution tree already shows what they do.

## EXECUTION TREE (Your primary source)

```
{execution_tree}
```

This tree shows:
- Every class in execution order with file paths
- Every resource (package, file, service, etc.) with ALL its attributes
- All conditionals (if/unless/case) and what they check
- All loops (.each) with the collection being iterated
- Relationship chains (-> and ~>)

## DIRECTORY LISTING

```
{directory_listing}
```

Use these exact paths in your File Structure section.

## EXTERNAL DEPENDENCIES

```
{dependencies_summary}
```

## CUSTOM TYPES AND PROVIDERS

```
{custom_types_summary}
```

## PUPPETDB USAGE

```
{puppetdb_summary}
```

## CREDENTIALS

```
{credentials_summary}
```

## CONTROL REPO CONTEXT

```
{control_repo_summary}
```

---

# YOUR TASK

Write a detailed migration plan by walking through the execution tree step-by-step.

**Step 1:** Use the `parse_hiera_config` tool

**Step 2:** Use `read_file` to read the Hiera YAML files shown by parse_hiera_config

**Step 3:** Write the migration plan following the template and examples from the system prompt

---

# CRITICAL RULES

1. **Use the execution tree as your source** - Every resource, class, and relationship is shown there
2. **List ALL resource details** - Package names, file paths, service names, template mappings, exact attribute values
3. **Expand iterations** - When the tree shows a loop, list every item explicitly by name (get names from Hiera data)
4. **Follow the tree into dependencies** - When a class includes another class, describe what that class does by following its branch in the tree
5. **Be specific** - Use exact paths, exact package names, exact ports, exact configuration values
6. **No vague language** - Never say "configures X" or "sets up Y" - say exactly what packages, files, services are managed
7. **Follow the examples** - The system prompt has detailed examples showing the level of detail expected

---

# WHAT NOT TO DO

- Don't read manifest files (.pp) - use the execution tree instead
- Don't read template files (.erb, .epp) - they're already analyzed
- Don't say "for each item" - list the items explicitly
- Don't be vague - be specific about every resource
- Don't skip dependency modules - expand into them and describe what they do

---

# OUTPUT FORMAT

Your response should be markdown text following the template from the system prompt.

Look at the **GOOD EXAMPLES** in the system prompt - that's the level of detail expected.

**File Structure:** One file per line, exact paths from directory listing above

**Module Explanation:** Walk through the execution tree, listing:
- Exact package names
- File paths with modes and owners
- Template source → destination mappings
- Service names with ensure/enable values
- All loop iterations with explicit item names from Hiera
- Resource counts per class

