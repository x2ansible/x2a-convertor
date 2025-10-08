# Nginx Ansible Role (Migrated from Chef)

This directory contains an Ansible role for deploying and managing Nginx, migrated from a Chef cookbook based on the provided "Module Migration Plan".

**IMPORTANT:** This migration was performed without access to the original Chef cookbook source code. The Ansible role is based solely on the textual description in the migration plan. While efforts were made to ensure functional parity, semantic identicality with the original Chef cookbook cannot be fully guaranteed.

## Structure

- `playbook.yml`: The main playbook to run the Nginx role.
- `roles/nginx/`:
    - `defaults/main.yml`: Default variables for Nginx installation and configuration.
    - `handlers/main.yml`: Handlers for Nginx service restart/reload, including a config test.
    - `meta/main.yml`: Metadata for the Ansible role.
    - `tasks/main.yml`: The core logic for installing, configuring, and managing Nginx, translated from Chef resources.
    - `templates/`:
        - `nginx.conf.j2`: Jinja2 template for the main Nginx configuration.
        - `default-site.conf.j2`: Jinja2 template for the default Nginx site.
        - `nginx_site.j2`: A generic Jinja2 template for custom Nginx sites.
    - `vars/`:
        - `Debian.yml`: Platform-specific variables for Debian-based systems.
        - `RedHat.yml`: Platform-specific variables for RedHat-based systems.

## Usage

1.  **Review Variables:** Adjust variables in `roles/nginx/defaults/main.yml` or create a `host_vars`/`group_vars` file to override defaults.
2.  **Define Nginx Sites:** To add custom Nginx sites, define the `nginx_sites` variable in your inventory or host/group vars. Example:

    ```yaml
    nginx_sites:
      - name: "my_webapp"
        template: "my_webapp.conf.j2" # Optional, if using a custom template
        enabled: true
        listen_port: 80
        server_name: "mywebapp.example.com"
        root: "/var/www/mywebapp"
        index: "index.html"
      - name: "another_site"
        enabled: false # This site will be disabled
        # ... other site parameters
    ```

    If using a custom template (e.g., `my_webapp.conf.j2`), place it in `roles/nginx/templates/`.

3.  **Run the Playbook:**

    ```bash
    ansible-playbook -i your_inventory playbook.yml
    ```

## Role Features (Based on Migration Plan)

-   **Nginx Installation:** Supports installation from distribution packages or official Nginx repositories (mainline/stable).
-   **Configuration Management:** Manages `/etc/nginx/nginx.conf`, creates necessary directories (`conf.d`, `sites-available`, `sites-enabled`), and a default site.
-   **Service Management:** Ensures the Nginx service is running and enabled, and performs configuration syntax tests before restarts/reloads.
-   **Virtual Host Management:** Allows defining and managing multiple Nginx virtual host configurations (sites), including enabling and disabling them.

