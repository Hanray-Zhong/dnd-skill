"""固定 Markdown 规则章节库的只读运行时。"""

from dnd_5e.rules.library import (
    RulesLibrary,
    default_library_root,
    installed_library_identity,
)

__all__ = ["RulesLibrary", "default_library_root", "installed_library_identity"]
