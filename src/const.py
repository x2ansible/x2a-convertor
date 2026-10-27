"""Constants used throughout the application."""

# Migration plan filenames
MIGRATION_PLAN_FILE = "migration-plan.md"

# Module migration plan filename template
MODULE_MIGRATION_PLAN_TEMPLATE = "migration-plan-{module}.md"

# Heading of the module list in the migration plan. The plan generation prompt
# (init_migration_instructions.md) and the metadata extraction prompts
# (init_metadata_extraction_{system,task}.md) depend on it.
MODULE_INVENTORY_HEADING = "MODULE INVENTORY"

# Metadata filename
METADATA_FILENAME = "generated-project-metadata.json"

INPUT_AGENTS_FILE = "INPUT-AGENTS.md"
EXPORT_AGENTS_FILE = "EXPORT-AGENTS.md"

X2A_ORIGINAL_MESSAGE = "x2a_original_message"


ADVERSARIAL_REPORT_FILENAME = "agent-adversarial-report.json"
