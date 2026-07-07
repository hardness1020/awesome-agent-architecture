"""Section 19 offline checks, no key, no network.

An in-process FakeServer stands in for an MCP server: it answers list_tools and
call the way a real stdio/http transport would, minus the wire.

test_connect(): discovery wraps each tool, namespaces and normalizes its name,
maps the readOnlyHint annotation to the permission hint, carries the schema, and
run() calls back through to the server with the bare tool name.

test_namespace(): weird names are sanitized to the API charset, and two servers
that expose a same-named tool stay distinct under the mcp__server__tool namespace.

test_pool_and_gate(): MCP tools merge into the same Registry as built-ins, and
the permission gate (section 3) reads the annotation-derived hint keyed on the
fully qualified name, so a rule can gate an MCP tool by its qualified name.

test_merge_servers(): plugin/user/project/local config layers by precedence.

test_channel(): a server push wraps into the <channel> tag.

    python sections/19-mcp-plugins-channels/src/test.py
"""
import mcp
import permissions
from permissions import DEFAULT, PLAN
from tools import Registry, Tool, run_tool


class FakeServer:
    """In-process stand-in for an MCP server. Real deployments reach it over
    stdio/http/sse; here it answers directly so the checks need no wire."""

    def __init__(self, tools):
        self._tools = tools          # list of tool specs: the tools/list payload
        self.calls = []              # recorded so a test can prove the pass-through

    def list_tools(self):
        return self._tools

    def call(self, tool, args):
        self.calls.append((tool, args))
        return f"{tool}({args})"


def kb_server():
    return FakeServer([
        {"name": "search", "description": "search the KB",
         "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
         "annotations": {"readOnlyHint": True}},
        {"name": "delete-page", "description": "delete a page",
         "annotations": {"destructiveHint": True}},          # not read-only: a side effect
    ])


def test_connect():
    srv = kb_server()
    by = {t.name: t for t in mcp.connect("docs-kb", srv)}

    # discovery wrapped each tool and namespaced it mcp__<server>__<tool>
    assert set(by) == {"mcp__docs-kb__search", "mcp__docs-kb__delete-page"}
    # the readOnlyHint annotation became the permission hint the gate reads
    assert by["mcp__docs-kb__search"].is_read_only is True
    assert by["mcp__docs-kb__delete-page"].is_read_only is False
    # the advertised schema carried from the spec
    assert by["mcp__docs-kb__search"].input_schema["properties"] == {"q": {"type": "string"}}
    # run() calls out over the transport with the bare tool name restored
    out = run_tool(by["mcp__docs-kb__search"], {"q": "locks"})
    assert srv.calls == [("search", {"q": "locks"})]
    assert out == "search({'q': 'locks'})"

    print("19 mcp: connect ok")


def test_namespace():
    # a name with chars outside [a-zA-Z0-9_-] is sanitized (normalizeNameForMCP)
    assert mcp.tool_name("my server/1", "read file!") == "mcp__my_server_1__read_file_"

    # two servers expose a same-named tool; the namespace keeps them distinct
    reg = Registry()
    for t in mcp.connect("alpha", FakeServer([{"name": "search"}])):
        reg.register(t)
    for t in mcp.connect("beta", FakeServer([{"name": "search"}])):
        reg.register(t)
    assert reg.get("mcp__alpha__search") is not None
    assert reg.get("mcp__beta__search") is not None
    assert len({s["name"] for s in reg.schemas()}) == 2       # no collision

    print("19 mcp: namespace ok")


def test_pool_and_gate():
    # MCP tools merge into the SAME pool as built-ins; the loop dispatches all alike
    reg = Registry()
    reg.register(Tool(name="LocalEcho", run=lambda a: a.get("x"), is_read_only=True))
    for t in mcp.connect("docs-kb", kb_server()):
        reg.register(t)
    names = {s["name"] for s in reg.schemas()}
    assert "LocalEcho" in names and "mcp__docs-kb__search" in names

    read = reg.get("mcp__docs-kb__search")
    write = reg.get("mcp__docs-kb__delete-page")
    # the gate keys on the annotation-derived hint (section 3)
    assert permissions.decide(read, DEFAULT, set()) == "allow"      # readOnlyHint -> allow
    assert permissions.decide(write, DEFAULT, set()) == "ask"       # side effect -> ask a human
    # a rule keyed on the fully qualified name pre-approves the write
    assert permissions.decide(write, DEFAULT, {"mcp__docs-kb__delete-page"}) == "allow"
    # plan mode: reads run, writes wait for the plan
    assert permissions.decide(read, PLAN, set()) == "allow"
    assert permissions.decide(write, PLAN, set()) == "deny"

    print("19 mcp: pool and gate ok")


def test_merge_servers():
    plugin = {"plugin": {"kb": {"url": "plugin-kb"}, "fs": {"url": "fs"}}}
    project = {"project": {"kb": {"url": "project-kb"}}}
    local = {"local": {"kb": {"url": "local-kb"}}}
    merged = mcp.merge_servers(plugin, project, local)
    assert merged["kb"]["url"] == "local-kb"       # local wins over project over plugin
    assert merged["fs"]["url"] == "fs"             # a plugin-only server survives

    print("19 mcp: merge ok")


def test_channel():
    assert mcp.wrap_channel("slack", "deploy finished") == \
        '<channel source="slack">deploy finished</channel>'

    print("19 mcp: channel ok")


def test_gate_inbound():
    # no gates: same tagged message wrap_channel produces
    assert mcp.gate_inbound("slack", "deploy finished") == \
        '<channel source="slack">deploy finished</channel>'

    # a gate drops spam before the loop ever sees it; other messages pass
    spam = lambda source, payload: {"drop": True} if "win a prize" in payload else None
    assert mcp.gate_inbound("sms", "win a prize now!!", gates=[spam]) is None
    assert mcp.gate_inbound("sms", "build is green", gates=[spam]) is not None

    # a gate rewrites (redacts) the payload; gates run in order
    redact = lambda source, payload: {"rewrite": payload.replace("hunter2", "[redacted]")}
    out = mcp.gate_inbound("slack", "the password is hunter2", gates=[spam, redact])
    assert out == '<channel source="slack">the password is [redacted]</channel>'

    print("19 mcp: inbound gate ok")


if __name__ == "__main__":
    test_connect()
    test_namespace()
    test_pool_and_gate()
    test_merge_servers()
    test_channel()
    test_gate_inbound()
