from langchain_community.tools.file_management.file_search import FileSearchTool


def list_files(path: str) -> [str]:
    """Get a directory listing as an array of strings"""
    search_tool = FileSearchTool()
    files = search_tool.run({"dir_path": path, "pattern": "*"}).splitlines()
    return [f"{path}/{x}" for x in files]
