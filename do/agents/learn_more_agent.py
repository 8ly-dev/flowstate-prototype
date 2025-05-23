"""
This module contains the LearnMoreAgent class for providing information about the application.
"""

from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING

from do.agents.base_agent import Agent, tool
from do.db_models import User


if TYPE_CHECKING:
    from do.chats import LearnMoreChat


class LearnMoreAgent(Agent):
    """You don't have a name, you are an authoritative representative of our company, 8ly, our first app, Do, and
    me, Zech, the founder.

    Your purpose is to communicate the goals and values of 8ly and the value of Do to investors and potential
    co-founders. You're also tasked with discussing the prototype's codebase with the goal of demonstrating the
    feasibility of the project using existing technologies and putting the user at ease that we understand what to do.
    Make your messages as clear and scannable as possible. Review the project's README file before addressing
    questions about the codebase.

    Use tools to look up all relevant documents to help you answer any questions the user may have. If the user asks
    technical questions about how the Do prototype functions, you can look through the relevant code files.
    These documents are your understanding, don't refer to them as documents.

    BE AWARE:
    The code is solely intended for demonstration purposes. It is not intended for production use. The actual finished
    version of Do is not yet created. The code you have access to is ONLY for the prototype and IS NOT
    representative of the actual version that is coming. When discussing the prototype's code, focus on the
    technologies and the patterns used.

    Guidelines:
    - Never refer to yourself as an AI, agent, or assistant.
    - Don't talk about Do as an app, use the name Do instead.
    - Respond and act in a way that feels intuitive, supportive, and innately human.
    - When the user goes off-topic, redirect them back to discuss Do and 8ly.
    - Don't overuse the user's name, it's ok occasionally.
    - Don't refer to yourself or the company in the first person.
    - If the documents don't have a clear answer for the user's question, offer a generic answer with a probable
    expectation.
    - When sharing links, use markdown link formatting.

    ALWAYS surface information relevant to the user's question to avoid the need for followup questions.
    ALWAYS validate technical answers against the codebase.
    NEVER guess about technical details (tech stack, languages used, technologies planned, etc.), always refer to the documents.

    Whatever you do: NEVER EVER make anything up. All necessary information is available in the documents."""
    def __init__(self, user: User | None, chat: "LearnMoreChat"):
        """
        Initialize the LearnMoreAgent with user information and WebSocket connection.

        Args:
            user: Optional user information
            chat: WebSocket connection for sending messages to the client
        """
        root = Path(__file__).parent.parent.parent
        readme_path = root / "README.md"
        with readme_path.open("r") as f:
            self.readme = f.read()

        if user:
            self.system_prompt += (
                f"\n\nThe user is currently logged in as {user.username}. Use the user's name from "
                f"time to time, as is appropriate.\n\n"
            )

        self._chat = chat
        self._file_cache = {}
        self._path_cache = []
        self._root = Path(__file__).parent.parent.parent
        super().__init__(self._chat.send_using)

    @tool("Creating GitHub link")
    async def create_github_link(self, file_path: str = "") -> str:
        """Creates a link to the file on GitHub. If no file path is given it returns the repo link."""
        if not file_path:
            return "https://github.com/8ly-dev/do-prototype"

        return f"https://github.com/8ly-dev/do-prototype/blob/main/{file_path}"

    @tool("Listing files")
    async def list_files(self) -> list[str]:
        """Activate this tool whenever you need to know what documents are available to you to answer the user's
        questions."""
        files = self._find_files()
        print("LISTING FILES", files)
        return files

    @tool(lambda file_path: f"Reading file {file_path.split('/')[-1]}")
    async def read_file(self, file_path: str):
        """Activate this tool whenever you need to read a document. Use the file path to locate the file. If the file
        doesn't exist, you'll get an error message back."""
        print(f"READING (input): {file_path}")
        
        # Normalize the input file_path to lowercase for consistent lookups
        # as the agent might be fed lowercase names due to normalization.
        requested_file_lower = file_path.lower()

        await self._chat.send_using(f"Reading {file_path.split('/')[-1]}") # Display based on input

        # Check cache using the lowercased version
        if requested_file_lower in self._file_cache:
            return self._file_cache[requested_file_lower]

        # _find_files() now returns paths with original casing, relative to root.
        available_files_original_case = self._find_files()
        
        path_to_open_relative = None
        for original_cased_file_rel in available_files_original_case:
            if original_cased_file_rel.lower() == requested_file_lower:
                path_to_open_relative = original_cased_file_rel
                break

        if path_to_open_relative is None:
            print(f"- Access denied: Normalized '{requested_file_lower}' not found in available files.")
            return f"Access denied: File {file_path} not found."

        actual_path_on_disk = self._root / path_to_open_relative
        print(f"- Attempting to open: {str(actual_path_on_disk)}")
        try:
            with actual_path_on_disk.open("r") as f:
                file_content = f.read()
            # Cache with the lowercased key for consistent future lookups
            self._file_cache[requested_file_lower] = file_content
            print(f"- Successfully read '{str(actual_path_on_disk)}'. Content: '{file_content[:20]}...")
            return file_content
        except FileNotFoundError:
            # This case should ideally not be hit if _find_files is accurate and filesystem is consistent
            print(f"- FileNotFoundError for: {str(actual_path_on_disk)} despite being in available list.")
            return f"Error: File {file_path} could not be opened (unexpectedly not found)."
        except Exception as e:
            print(f"- Error opening {str(actual_path_on_disk)}: {e}")
            return f"Error opening file {file_path}."

    def _find_files(self, path: Path | None = None) -> list[str]:
        """
        Find all files in the project directory.

        This method recursively searches for files in the project directory,
        excluding hidden files and directories.

        Args:
            path: Optional path to search in, defaults to the project root

        Returns:
            A list of file paths (with original casing) relative to the project root
        """
        if not path and self._path_cache:
            return self._path_cache

        _path = path or self._root
        if _path.name.startswith("."):
            return []

        if _path.is_file():
            # Return path relative to self._root, preserving case
            return [str(_path.relative_to(self._root))]

        files = list(chain(*(self._find_files(child) for child in _path.iterdir())))
        if not path: # Caching the result if it's the initial call
            self._path_cache = files

        return files