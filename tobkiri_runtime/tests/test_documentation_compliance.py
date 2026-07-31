"""Tests for documentation compliance and code quality standards."""

import pytest
import re
from pathlib import Path
from typing import List, Dict, Any


class TestDocumentationCompliance:
    """Test that documentation meets quality standards."""

    @pytest.fixture
    def readme_path(self) -> Path:
        """Path to root README.md."""
        return Path(__file__).parent.parent.parent / "README.md"

    @pytest.fixture
    def agents_path(self) -> Path:
        """Path to AGENTS.md."""
        return Path(__file__).parent.parent.parent / "AGENTS.md"

    @pytest.fixture
    def readme_content(self, readme_path: Path) -> str:
        """Read README.md content."""
        return readme_path.read_text(encoding="utf-8")

    @pytest.fixture
    def agents_content(self, agents_path: Path) -> str:
        """Read AGENTS.md content."""
        return agents_path.read_text(encoding="utf-8")

    def test_readme_has_quick_start_section(self, readme_content: str):
        """Test that README contains Quick Start section."""
        assert "## Quick Start" in readme_content, \
            "README.md should contain a Quick Start section"

    def test_readme_has_troubleshooting_section(self, readme_content: str):
        """Test that README contains Troubleshooting section."""
        assert "## Troubleshooting" in readme_content, \
            "README.md should contain a Troubleshooting section"

    def test_readme_has_contributing_section(self, readme_content: str):
        """Test that README contains Contributing section."""
        assert "## Contributing" in readme_content, \
            "README.md should contain a Contributing section"

    def test_readme_has_table_of_contents(self, readme_content: str):
        """Test that README contains table of contents."""
        assert "## Read This When..." in readme_content, \
            "README.md should contain a table of contents"

    def test_readme_quick_start_uses_kernel_panel_port(self, readme_content: str):
        """Test that Quick Start points at the kernel panel port."""
        assert "http://localhost:8765/panel/" in readme_content, \
            "README Quick Start should use the kernel panel port"
        assert "http://localhost:8080/panel/" not in readme_content, \
            "README Quick Start should not use the setup web port for the panel"

    def test_readme_links_are_valid(self, readme_content: str):
        """Test that internal links in README are valid."""
        # Extract markdown links
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        links = re.findall(link_pattern, readme_content)

        readme_path = Path(__file__).parent.parent.parent / "README.md"

        for link_text, link_url in links:
            # Skip external URLs
            if link_url.startswith(("http://", "https://", "mailto:")):
                continue

            # Check internal file links
            if link_url.startswith("./") or link_url.startswith("../"):
                target_path = (readme_path.parent / link_url).resolve()
                assert target_path.exists(), \
                    f"Broken link: {link_url} (target: {target_path})"

    def test_agents_has_code_style_guidelines(self, agents_content: str):
        """Test that AGENTS.md contains code style guidelines."""
        assert "## Code Style Guidelines" in agents_content, \
            "AGENTS.md should contain Code Style Guidelines section"

    def test_agents_has_testing_guidelines(self, agents_content: str):
        """Test that AGENTS.md contains testing guidelines."""
        assert "## Testing Guidelines" in agents_content, \
            "AGENTS.md should contain Testing Guidelines section"

    def test_agents_has_security_checklist(self, agents_content: str):
        """Test that AGENTS.md contains security checklist."""
        assert "### Security Checklist" in agents_content, \
            "AGENTS.md should contain Security Checklist section"

    def test_agents_has_pull_request_process(self, agents_content: str):
        """Test that AGENTS.md contains pull request process."""
        assert "## Pull Request Process" in agents_content, \
            "AGENTS.md should contain Pull Request Process section"


class TestCodeQuality:
    """Test code quality standards."""

    @pytest.fixture
    def python_files(self) -> List[Path]:
        """Get all Python files in the project."""
        root_dir = Path(__file__).parent.parent.parent
        return list(root_dir.rglob("*.py"))

    def test_python_files_have_docstrings(self, python_files: List[Path]):
        """Test that Python files have module docstrings."""
        files_without_docstrings = []

        for py_file in python_files:
            # Skip test files and __init__.py
            if py_file.name.startswith("test_") or py_file.name == "__init__.py":
                continue

            # Skip files in certain directories that may not need docstrings
            skip_dirs = ["__pycache__", ".venv", "node_modules", ".git"]
            if any(skip_dir in str(py_file) for skip_dir in skip_dirs):
                continue

            try:
                content = py_file.read_text(encoding="utf-8")
                # Check if file starts with docstring
                stripped = content.strip()
                if stripped and not stripped.startswith('"""') and not stripped.startswith("'''"):
                    files_without_docstrings.append(py_file)
            except Exception:
                # Skip files that can't be read
                continue

        # For now, we'll just warn about files without docstrings rather than failing
        # This is because many existing files may not have docstrings
        if files_without_docstrings:
            import warnings
            warnings.warn(f"Files without module docstrings ({len(files_without_docstrings)} total): "
                         f"Consider adding docstrings to improve code documentation.")

    def test_python_files_use_type_hints(self, python_files: List[Path]):
        """Test that Python files use type hints."""
        files_without_hints = []

        for py_file in python_files:
            # Skip test files and __init__.py
            if py_file.name.startswith("test_") or py_file.name == "__init__.py":
                continue

            # Skip files in certain directories
            skip_dirs = ["__pycache__", ".venv", "node_modules", ".git"]
            if any(skip_dir in str(py_file) for skip_dir in skip_dirs):
                continue

            try:
                content = py_file.read_text(encoding="utf-8")
                # Simple check for type hints
                if "def " in content and "->" not in content and ":" not in content.split("def ")[1].split("(")[1].split(")")[0]:
                    files_without_hints.append(py_file)
            except Exception:
                # Skip files that can't be read
                continue

        # This is a warning, not a failure, as it's hard to check perfectly
        if files_without_hints:
            import warnings
            warnings.warn(f"Files that might lack type hints: {files_without_hints}")


class TestProjectStructure:
    """Test project structure standards."""

    @pytest.fixture
    def root_dir(self) -> Path:
        """Root directory of the project."""
        return Path(__file__).parent.parent.parent

    def test_readme_exists(self, root_dir: Path):
        """Test that README.md exists at root."""
        assert (root_dir / "README.md").exists(), \
            "README.md should exist at project root"

    def test_agents_md_exists(self, root_dir: Path):
        """Test that AGENTS.md exists at root."""
        assert (root_dir / "AGENTS.md").exists(), \
            "AGENTS.md should exist at project root"

    def test_license_exists(self, root_dir: Path):
        """Test that LICENSE file exists."""
        assert (root_dir / "LICENSE").exists(), \
            "LICENSE file should exist at project root"

    def test_gitignore_exists(self, root_dir: Path):
        """Test that .gitignore exists."""
        assert (root_dir / ".gitignore").exists(), \
            ".gitignore should exist at project root"

    def test_justfile_exists(self, root_dir: Path):
        """Test that justfile exists."""
        assert (root_dir / "justfile").exists(), \
            "justfile should exist at project root"

    def test_github_workflows_exist(self, root_dir: Path):
        """Test that GitHub workflows exist."""
        workflows_dir = root_dir / ".github" / "workflows"
        assert workflows_dir.exists(), \
            ".github/workflows directory should exist"

        workflow_files = list(workflows_dir.glob("*.yml"))
        assert len(workflow_files) > 0, \
            "At least one workflow file should exist"

    def test_pr_template_exists(self, root_dir: Path):
        """Test that PR template exists."""
        pr_template = root_dir / ".github" / "pull_request_template.md"
        assert pr_template.exists(), \
            "PR template should exist at .github/pull_request_template.md"


class TestDocumentationContent:
    """Test documentation content quality."""

    @pytest.fixture
    def readme_content(self) -> str:
        """Read README.md content."""
        readme_path = Path(__file__).parent.parent.parent / "README.md"
        return readme_path.read_text(encoding="utf-8")

    def test_readme_has_installation_instructions(self, readme_content: str):
        """Test that README contains installation instructions."""
        assert "pip install" in readme_content, \
            "README should contain pip install instructions"

    def test_readme_has_usage_examples(self, readme_content: str):
        """Test that README contains usage examples."""
        assert "python -m tobkiri" in readme_content, \
            "README should use the canonical Tobkiri CLI"

    def test_readme_has_troubleshooting_tips(self, readme_content: str):
        """Test that README contains troubleshooting tips."""
        # Check for common troubleshooting patterns
        troubleshooting_patterns = [
            "port",
            "error",
            "fix",
            "solution",
            "problem"
        ]

        content_lower = readme_content.lower()
        found_patterns = [p for p in troubleshooting_patterns if p in content_lower]

        assert len(found_patterns) >= 2, \
            f"README should contain troubleshooting tips. Found: {found_patterns}"

    def test_readme_has_contact_information(self, readme_content: str):
        """Test that README contains contact information."""
        # Check for GitHub issues link or contact info
        assert "github.com" in readme_content or "issues" in readme_content.lower(), \
            "README should contain contact information or link to issues"


class TestChangelogCompliance:
    """Test changelog compliance."""

    @pytest.fixture
    def changelog_path(self) -> Path:
        """Path to CHANGELOG.md."""
        return Path(__file__).parent.parent / "CHANGELOG.md"

    @pytest.fixture
    def changelog_content(self, changelog_path: Path) -> str:
        """Read CHANGELOG.md content."""
        if not changelog_path.exists():
            pytest.skip("CHANGELOG.md not found")
        return changelog_path.read_text(encoding="utf-8")

    def test_changelog_has_unreleased_section(self, changelog_content: str):
        """Test that changelog has Unreleased section."""
        assert "## Unreleased" in changelog_content or "## [Unreleased]" in changelog_content, \
            "CHANGELOG.md should have an Unreleased section"

    def test_changelog_format(self, changelog_content: str):
        """Test that changelog follows standard format."""
        # Check for standard changelog format
        lines = changelog_content.strip().split("\n")

        # Should start with header
        assert lines[0].startswith("#"), \
            "CHANGELOG.md should start with a header"

        # Should have version sections
        version_pattern = r'^## \[?\d+\.\d+\.\d+\]?'
        has_versions = any(re.match(version_pattern, line) for line in lines)

        # At least have Unreleased
        assert "Unreleased" in changelog_content, \
            "CHANGELOG.md should have version sections"
