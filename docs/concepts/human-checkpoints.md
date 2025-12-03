---
layout: default
title: Human Checkpoints
parent: Concepts
nav_order: 3
---

# Human-in-the-Loop Checkpoints

X2A Convertor integrates human review at critical decision points to ensure quality, compliance, and correctness.

## Why Human Checkpoints?

AI-powered automation accelerates migration but cannot replace human judgment for:

- **Architectural decisions**: Migration priority, module grouping
- **Business logic validation**: Edge cases, regulatory requirements
- **Risk assessment**: Production impact, rollback strategies
- **Quality gates**: Compliance with organizational standards

```mermaid
flowchart LR
    AI[AI Agent<br/>Fast, consistent] --> Output[Generated Artifact]
    Output --> Human{Human Review<br/>Strategic, contextual}
    Human -->|Approve| Next[Next Phase]
    Human -->|Refine| AI
    Human -->|Manual Fix| Manual[Manual Intervention]

    style AI fill:#e3f2fd
    style Human fill:#fff3e0
    style Next fill:#e8f5e9
```

## Checkpoint 1: Init Plan Review

### Trigger

After `app.py init` completes

### Artifact

`migration-plan.md`

### Review Checklist

#### Repository Structure

- [ ] All expected cookbooks/modules identified
- [ ] No critical modules missing
- [ ] External dependencies correctly detected

#### Dependency Analysis

- [ ] Dependency graph accurate
- [ ] Circular dependencies flagged
- [ ] External Supermarket cookbooks noted

#### Migration Strategy

- [ ] Recommended order aligns with deployment architecture
- [ ] Critical infrastructure components prioritized appropriately
- [ ] Complexity estimates reasonable

### Decision Points

1. **Adjust migration order**

   ```bash
   # Re-run with specific guidance
   uv run app.py init --source-dir ./chef-repo \
     "Prioritize security and compliance cookbooks first"
   ```

2. **Exclude certain modules**

   - Document exclusions in plan
   - Handle manually or defer

3. **Approve and proceed**
   - Commit `migration-plan.md` to version control
   - Move to analyze phase

## Checkpoint 2: Module Specification Review

### Trigger

After `app.py analyze` completes for each module

### Artifact

`migration-plan-<module>.md`

### Review Checklist

#### File Mappings

- [ ] All recipes are described
- [ ] Templates correctly identified for conversion
- [ ] Static files (files/) mapped appropriately

#### Variable Mapping

- [ ] Node attributes mapped to facts/variables
- [ ] Secrets and sensitive data flagged

### Decision Points

1. **Request refinement**

   ```bash
   # Re-run with clarifications
   uv run app.py analyze --source-dir ./chef-repo \
     "Focus on SSL configuration details in nginx-multisite"
   ```

2. **Manual specification adjustments**

   - Edit `migration-plan-<module>.md` directly
   - Document custom translation requirements

3. **Approve and proceed**
   - Commit specification
   - Trigger migrate phase

## Checkpoint 3: Generated Code Review

### Trigger

After `app.py migrate` completes

### Artifact

`ansible/roles/<module>/` directory

### Review Checklist

#### Structure

- [ ] Role follows Ansible best practices
- [ ] Files organized in standard directories
- [ ] Naming conventions consistent

#### Task Logic

- [ ] Task order matches recipe execution
- [ ] Idempotency maintained
- [ ] Error handling appropriate

#### Templates

- [ ] Jinja2 syntax correct
- [ ] Variables match defaults
- [ ] Conditional blocks translated

#### Lint Status

- [ ] No ansible-lint errors
- [ ] Warnings addressed or documented
- [ ] Code passes organization standards

### Example Review

```yaml
# ansible/nginx-multisite/tasks/main.yml
---
- name: Install nginx
  package:
    name: nginx
    state: present
  tags: ["nginx", "packages"]

- name: Configure nginx main config
  template:
    src: nginx.conf.j2
    dest: /etc/nginx/nginx.conf
    owner: root
    group: root
    mode: "0644"
  notify: Reload nginx

- name: Ensure nginx is running
  service:
    name: nginx
    state: started
    enabled: true
  tags: ["nginx", "service"]
```

**What to Look For:**

- Does execution order match Chef recipe?
- Are handlers properly defined and notified?
- Are tags useful for selective runs?

### Testing Recommendations

Before production, test in isolated environment:

```bash
# Syntax check
ansible-playbook --syntax-check site.yml

# Dry run
ansible-playbook --check site.yml

# Run against test server
ansible-playbook -i test-inventory site.yml --tags nginx

# Verify idempotency
ansible-playbook -i test-inventory site.yml --tags nginx
# Second run should show no changes
```

### Decision Points

1. **Iterate on generation**

   ```bash
   # Adjust and regenerate
   uv run app.py migrate ... "Fix handler naming to match organizational standards"
   ```

2. **Manual fixes**

   - Edit generated files directly
   - Document changes for future reference

3. **Approve and proceed to publish**
   - Commit generated role
   - Proceed to publish phase

## Checkpoint 4: Published Deployment Review

### Trigger

After `app.py publish` completes

### Artifact

- GitOps repository: `{role}-gitops` on GitHub
- Local deployment directory: `ansible/deployments/{role}/`

### Review Checklist

#### Deployment Structure

- [ ] All required directories created (`roles/`, `playbooks/`, `aap-config/`, `.github/workflows/`)
- [ ] Role copied correctly to `roles/{role}/`
- [ ] Deployment structure follows GitOps conventions

#### Generated Configurations

- [ ] Playbook (`{role}_deploy.yml`) references correct role
- [ ] Job template (`{role}_deploy.yaml`) configured for Ansible Automation Platform
- [ ] GitHub Actions workflow (`deploy.yml`) has proper CI/CD steps
- [ ] All file paths and references are correct

#### Repository Status

- [ ] GitHub repository created successfully
- [ ] Branch pushed to remote
- [ ] Repository visibility appropriate (public/private)
- [ ] Repository name follows convention (`{role}-gitops`)

#### Credentials and Access

- [ ] GitHub credentials working
- [ ] AAP credentials documented (if needed)
- [ ] Execution instructions clear in summary
- [ ] Repository URL accessible

### Example Review

After publishing `nginx_multisite`, verify:

```bash
# Check local deployment structure
ls -la ansible/deployments/nginx_multisite/

# Verify GitHub repository
gh repo view {owner}/nginx_multisite-gitops

# Check branch
gh api repos/{owner}/nginx_multisite-gitops/branches/main
```

### Decision Points

1. **Repository issues**

   - Delete and re-run if repository creation failed
   - Use `--skip-git` to generate files locally only for testing

2. **Configuration adjustments**

   - Edit generated files in deployment directory
   - Re-run publish if major changes needed

3. **Approve for production**
   - Repository ready for AAP integration
   - CI/CD pipeline can be triggered
   - Document any manual configuration steps needed

### Audit Trail

All checkpoints should be documented on git.
