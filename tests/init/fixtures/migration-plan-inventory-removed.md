# Migration Plan: Chef to Ansible

## Overview

Repository containing Chef cookbooks.

### MODULE INVENTORY

The repository contains two modules.

#### 1. `cache`
- **Path**: `cookbooks/cache`
- **Technology**: Chef
- **Description**: Installs and configures the cache service.

#### 2. `nginx-multisite`
- **Path**: `cookbooks/nginx-multisite`
- **Technology**: Chef
- **Description**: Configures nginx with multiple virtual hosts.

Inventory completeness: all cookbooks with recipes/default.rb are listed above.

### Infrastructure Files

- `cookbooks/fastapi-tutorial/Berksfile` is still present in the repository.

### Key Dependencies

- fastapi-tutorial depends on the cache cookbook.

### Migration Order

1. cache
2. nginx-multisite
3. fastapi-tutorial (effort: 2 days)
