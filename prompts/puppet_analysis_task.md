**Analyze the Puppet module at path: {path}**
**User requirements: {user_message}**

---

# DATA SOURCES

The execution tree, directory listing, dependencies, credentials, and control repo context are provided below. Do NOT re-read files already covered here.

## EXECUTION TREE (Primary source)

```
{execution_tree}
```

## DIRECTORY LISTING

```
{directory_listing}
```

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

# TASK

Write a migration plan by walking through the execution tree step-by-step.

1. Call `parse_hiera_config` ONCE, then read the Hiera YAML files it reports.
2. If the tree contains loops, read `init.pp` ONCE for class parameter defaults to resolve loop variables.
3. Write the migration plan using the format and examples from the system prompt. Resolve all Puppet variables to actual values.

**STOP after step 3.** You should need at most 5-8 tool calls total.

---

# KEY RULES

- Use the execution tree as your source — every resource and relationship is shown there
- Follow all formatting rules from the system prompt (compact resource-per-line format, resolved values, expanded loops)
- When a class includes another, walk through what that class does
- When a loop variable is empty: state "Loop runs 0 times" then describe the default/implicit instance with resolved values
- Do NOT read manifest files for execution order, read template files, or call `parse_hiera_config` more than once
