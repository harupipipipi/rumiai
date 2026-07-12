"""LoopEngine — main execution loop for agent interactions."""

import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from domain.agent.context_builder import ContextBuilder


class LoopEngine:
    """Executes the agent loop: build context, call LLM, check termination.

    MVP: simulates LLM calls with stub responses and stops after 1 iteration.
    Future: calls LLM via context capability_socket (defaults.ai.complete).
    """

    def run(self, agent_def, session, input_text, context):
        """Run the agent loop.

        Args:
            agent_def: dict with agent configuration (system_prompt, model, loop, etc.)
            session: AgentSession instance
            input_text: user input string
            context: handler context (contains capability_socket for future LLM calls)

        Returns:
            dict with messages, final_text, status, and metadata.
        """
        start_time = time.time()
        session.status = "running"
        session.add_message("user", input_text)

        max_iterations = agent_def.get("loop", {}).get("max_iterations", 10)
        context_builder = ContextBuilder()

        for _ in range(max_iterations):
            session.current_step += 1
            context_builder.build(agent_def, session, input_text)
            response_text = "[stub] Agent response for step " + str(session.current_step)
            session.add_message("assistant", response_text)
            session.total_tokens += len(response_text)
            break

        session.status = "completed"
        final_text = session.messages[-1]["content"] if session.messages else ""
        elapsed_ms = int((time.time() - start_time) * 1000)

        return {
            "messages": session.messages,
            "final_text": final_text,
            "status": "completed",
            "metadata": {
                "total_tokens": session.total_tokens,
                "steps": session.current_step,
                "elapsed_ms": elapsed_ms,
            },
        }
