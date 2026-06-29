"""Hermes Agent plugin registration for the Partner Follow-up Claw.

When Hermes loads this plugin, it calls ``register(ctx)`` which wires
each tool schema to its handler function.
"""

from .schemas import ALL_SCHEMAS
from .tools import HANDLERS


def register(ctx):
    """Register all Partner Follow-up Claw tools with the Hermes agent context."""
    schema_map = {s["name"]: s for s in ALL_SCHEMAS}

    for name, handler in HANDLERS.items():
        schema = schema_map.get(name)
        if schema:
            ctx.register_tool(schema=schema, handler=handler)
