<document>
How to fix some of the YAML validation issues

If a call of the ansible_write tool fails with an ERROR, you ALWAYS must to fix the issue and call the tool again until it returns successfully.
You MUST fix all issues on all lines at once before calling the ansible_write again.
If the issues persist after 10 or more attempts, rethink the file from the beginning.

Here is a list of Error examples and how to fix them:

- Error: [schema] $ ... is not of type 'array', 'null'
  - This error means the file has PLAYBOOK syntax but should have ROLE syntax
  - The file has a "tasks:" wrapper at the top level
  - example of WRONG YAML (playbook syntax with tasks: wrapper):
    ```yaml
    ---
    tasks:
      - name: Install nginx
        ansible.builtin.apt:
          name: nginx
          state: present
    ```
  - correctly formatted YAML should look like (role syntax - direct list):
    ```yaml
    ---
    - name: Install nginx
      ansible.builtin.apt:
        name: nginx
        state: present
    ```
  - how is it fixed: REMOVE the "tasks:" wrapper entirely. Task files in roles MUST be a direct list of tasks starting with "- name:", NOT wrapped in a "tasks:" key

- Error: Mapping values are not allowed in this context.
  - example of a wrong YAML fragment causing the error:
    - name: Set default deny policy
      ansible.builtin.command: ufw --force default deny
      when: ufw_status is not search('Default: deny')
  - correctly formatted YAML should look like:
    - name: Set default deny policy
      ansible.builtin.command: ufw --force default deny
      when: "ufw_status is not search('Default: deny')"
  - how is it fixed: the right-side string value of the "when:" key has been wrapped in double quotes ("") so it became just a string.

- Error: While parsing a block mapping did not find expected key.
  - example of a wrong YAML fragment causing the error:
    - dest: 'TEMPLATE_VARIABLE'/index.html
  - correctly formatted YAML should look like:
    - dest: 'TEMPLATE_VARIABLE/index.html'
  - how is it fixed: the whole right-side value of the "dest:" key has been fully wrapped in quotes (''), not just partially. The right side MUST be inside of quotes from its start to the end. DO NOT partially quote values.
</document>
