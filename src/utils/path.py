"""Path utilities.

Extended Path class with additional convenience methods.
"""

from pathlib import PosixPath as _PosixPath


class Path(_PosixPath):
    """Extended PosixPath with additional methods."""

    def relative_to_cwd(self) -> str:
        """Convert path to relative path from current working directory.

        Returns:
            String representation of relative path, or absolute path if conversion fails.
        """
        try:
            return str(self.relative_to(_PosixPath.cwd()))
        except ValueError:
            return str(self)
