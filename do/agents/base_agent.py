"""
This module contains the base Agent class for the Do application.
"""
import inspect
import traceback
from datetime import timedelta, timezone, UTC, datetime
from functools import wraps
from typing import Type

from pydantic_ai import Agent as PydanticAgent

from do.agents.utils import get_model


def tool(nice_name):
    def decorator(func):
        func.nice_name = nice_name
        return func

    return decorator


class Agent[DT, OT: str]:
    """
    Base agent class that provides common functionality for all agents.

    This class handles the initialization of the underlying PydanticAgent,
    manages the conversation history, and provides methods for sending prompts
    and using tools.

    Type Parameters:
        DT: The type of dependencies required by the agent
        OT: The output type of the agent's responses

    Attributes:
        agent_factory: Function that returns a language model instance
        system_prompt: The system prompt to use for the agent
        tools: List of tool methods available to the agent
        deps_type: The type of dependencies required by the agent
        output_type: The output type of the agent's responses
    """
    agent_factory = lambda _: get_model()
    system_prompt = ""
    tools = []
    deps_type: Type[DT] | None = None
    output_type: OT | None = None

    def __init__(self, report_tool = None, user_timezone: timezone | int = UTC):
        """
        Initialize the agent with an empty history and configure the underlying PydanticAgent.

        This sets up the agent with the appropriate system prompt, tools, and type information.
        """
        self.history = []
        self._report_tool_func = report_tool
        self.user_timezone = (
            user_timezone
            if isinstance(user_timezone, timezone)
            else timezone(timedelta(minutes=user_timezone))
        )

        kwargs = {}
        if self.deps_type:
            kwargs["deps_type"] = self.deps_type
        if self.output_type:
            kwargs["output_type"] = self.output_type

        self.agent = PydanticAgent(
            self.agent_factory(),
            system_prompt="Always format dates in a nice human format.\n" + self.system_prompt,
            tools=[self.__current_date] + [self.__create_tool(name) for name in self.tools],
            **kwargs,
        )

    def __init_subclass__(cls, **kwargs):
        """
        Initialize a subclass of Agent.

        This method is called when a subclass of Agent is created. It initializes the tools list
        and sets the system prompt from the class docstring.

        Args:
            **kwargs: Additional keyword arguments passed to the superclass
        """
        if cls.tools is Agent.tools:
            cls.tools = []

        super_attrs = dir(Agent)
        for name in dir(cls):
            if not name.startswith("_") and name not in super_attrs and callable(getattr(cls, name)):
                cls.tools.append(name)

        cls.system_prompt = cls.__doc__

    async def _report_tool(self, tool_name: str):
        if self._report_tool_func:
            await self._report_tool_func(tool_name)

    async def send_prompt(self, prompt: str, *, deps: DT | None = None, output_type: Type[OT] | None = None) -> OT:
        """
        Send a prompt to the agent and get a response.

        This method sends a prompt to the underlying PydanticAgent, updates the conversation
        history with the new messages, and returns the output.

        Args:
            prompt: The prompt to send to the agent
            deps: Optional dependencies to provide to the agent
            output_type: Optional output type to override the default

        Returns:
            The agent's response of type OT
        """
        kwargs = {}
        if deps:
            kwargs["deps"] = deps

        if output_type:
            kwargs["output_type"] = output_type

        try:
            response = await self.agent.run(prompt, message_history=self.history, **kwargs)
        except Exception as e:
            # Print the full stack trace and error
            print(f"Error sending prompt {prompt[10:]}...")
            traceback.print_exc()
            raise
        finally:
            print(f"Done sending prompt {prompt[10:]}...")

        self.history.extend(response.new_messages())
        return response.output

    def __create_tool(self, attr_name):
        tool = getattr(self, attr_name)

        @wraps(tool)
        async def run_tool(*args, **kwargs):
            print("Using tool:", attr_name)
            name_callable = getattr(tool, "nice_name", attr_name)
            if isinstance(name_callable, str):
                name_callable = name_callable.format

            signature = inspect.signature(tool)
            arguments = signature.bind(*args, **kwargs)
            try:
                name = name_callable(**arguments.arguments)
            except Exception as e:
                print(f"Error in tool {attr_name}: {e}")
                print(arguments.arguments)
                return f"Error: {e}"

            await self._report_tool(name)
            try:
                return await tool(*args, **kwargs)
            except Exception as e:
                print(f"Error in tool {attr_name}: {e}")
                return f"Error in tool {attr_name}: {e}"
            finally:
                print("Done using tool:", attr_name)

        run_tool.__doc__ = tool.__doc__
        return run_tool

    async def __current_date(self) -> str:
        """Helper method to get the current date UTC in the ISO-8601 format."""
        return datetime.now(self.user_timezone).isoformat()
