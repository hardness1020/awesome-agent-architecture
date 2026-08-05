# 2 · Tool runtime

[English](README.md) · [繁體中文](README.zh-TW.md) · **简体中文**

> 新增一项能力，就是注册一个工具。loop 维持不变。

agent loop 只能通过工具来行动。模型会发出一个结构化的 `tool_use` 区块，带有 `name` 与 `input`。

harness 把那个名称对应到代码。它验证输入、执行 handler，并返回结果。

这个 runtime 必须：

1. 告诉模型有哪些工具存在。
2. 描述每个工具的 input schema。
3. 依名称把每个 `tool_use` 路由出去。
4. 在可行时并行执行安全的调用。
5. 让庞大的工具目录仍可被探索。

没有这一层，模型能要求行动，却没有东西能真正执行那个行动。

如果只有一个 `bash` 工具，每一项能力都变成字符串处理。没有各别工具的验证或权限逻辑。

有两种失败常被算到模型头上，其实都是从这一层开始的：description 彼此重叠，模型就挑错工具；harness 半路改写了 input，编辑就失败。

---

## 机制

![机制图](assets/02-tool-runtime.png)

一个工具是一个小对象，带有名称、handler、schema 与几个判定式。registry 依名称存放工具。dispatch 拿名称去查表，找到就执行。

### New: the tool runtime

```python
@dataclass
class Tool:                                  # src/tools.py
    name: str
    run: Callable[[dict], Any]
    description: str = ""                      # advertised to the model
    input_schema: dict = ...                   # the Anthropic schema it accepts
    is_read_only: bool = False
    is_concurrency_safe: bool = False         # may batch in parallel
    is_edit: bool = False                     # read by the gate (section 3)

class Registry:                              # src/tools.py
    def register(self, tool): self._tools[tool.name] = tool   # add a handler
    def get(self, name):      return self._tools.get(name)    # dispatch = lookup
    def schemas(self):        ...             # the tools list handed to the model
```

- 一个工具是一个 dataclass。
- registry 是 `name -> tool`。
- 新增一项能力，就是注册一个 handler。
- `schemas()` 返回向模型公告的工具清单。
- `run_concurrently` 会把标记为 `is_concurrency_safe` 的工具批量执行。
- 不安全的调用维持顺序执行，所以写入不会相互竞争。

### How it integrates

第 1 章用的是内嵌的 `HANDLERS` dict。第 2 章把一个 `registry` 传进 loop，并把每个 `tool_use` 通过 `_dispatch` 路由：

```python
def run_turn(messages, model, registry, max_steps=10): # src/loop.py (now takes a registry)
    ...
    results = [_dispatch(b, registry)                   # was: run_tool(call)
               for b in response.content if b.type == "tool_use"]
    messages.append({"role": "user", "content": results})

def _dispatch(block, registry):              # resolve, run, wrap as a tool_result
    tool = registry.get(block.name)           # name -> tool
    content = run_tool(tool, block.input)
    return {"type": "tool_result", "tool_use_id": block.id, "content": content}
```

loop 主体其余部分维持不变。只有 dispatch 这一步现在改用 registry。

`_dispatch` 是下一个延伸点。第 3 章在那里加上权限关卡。第 4 章在那里加上 hook。

demo 为了清楚起见采用顺序 dispatch。真实的 runtime 会把安全调用批量化，并按需加载庞大的工具 schema。
接下来谈的，都是目录一变大就会冒出来的东西。

### Grouping and granularity

一份扁平的 registry 看不出目录长什么样子。工具依调用往哪个方向走、又碰到什么，可以分成五类：感知（读外面的世界）、
执行（改动它）、协作（找上另一个 agent）、事件触发（让外界把 agent 叫醒），还有跟用户沟通（找上人）。
第 6、12、16 章做协作那一类，第 13、14 章做事件触发，第 19 章做跟用户沟通的通道。这一章做的，是这五类都得靠的那一层。

粒度是同一类里面的选择。功能和用途重叠的工具就合并：一个 `read_document` 带一个类型参数，比每种文件格式各配一个读取工具好用。
参数差很多的就拆开，因为一堆互不相干的字段凑在一起，模型看不出哪些才该填，schema 一过载就容易挑错参数。

### Describing a tool

`description` 不是文档。模型在挑工具之前，能看到的只有它。写得好的 description 会讲清楚什么时候该用、哪些事它不做、
几个具体的参数例子、返回长什么样，还有调用它要付多少代价。与其再多写几句说明，不如附上几个真实的调用范例。
书里说加了范例效果提升很多，但那个数字没有出处，所以只取方向，别当成量级。

接着 harness 要把 input 原封不动地交下去。把引号规范化、把空白修掉，或是塞进一个模型根本没写的参数，都会让调用坏在模型看不见的地方：
它送出的 input 是对的，结果却说编辑没对上，transcript 里也找不到任何线索。该验证就验证、该拒绝就拒绝，就是不要偷偷改写。

有些参数存在的目的就是被忽略。像 `expected_price`、`expected_status` 这种检查用的参数，逼模型在调用真的跑起来之前，先讲出它以为的状况。
handler 一律不照着它做事，而是去读存下来的真实数据、依那份数据做决定，然后把对不上的地方记下来，最后一道关卡站的就是模型伪造不了的数据。
τ-bench 的评分也是这个做法：看数据库最后的状态，不看 agent 自己怎么说。

### Perception interfaces

感知工具返回的东西常常塞不下。所以搜索一次只回一页候选，外加一个 cursor；读取吃 offset 和 limit；截断一定要标出来，不能默默做掉。
代码搜索最看得出这几条规则的差别。四种做法，而且没有系统只用其中一种：

| 做法 | 找得到什么 | 代价 |
| --- | --- | --- |
| **Glob** | 依路径模式找文件。 | 对内容一无所知。 |
| **Grep** | 精确字符串和 regex，附行号。 | 要调用好几次才收敛。同义词找不到。 |
| **Embedding 索引** | 依语义找代码，用白话问也问得到。 | 索引要建、还要一直同步。排序说不清楚。 |
| **LSP symbols** | 定义、引用、类型，一找一个准。 | 每种语言都要一个 language server。 |

Claude Code 不建索引，靠 agent 自己搜：先 glob、再 grep、然后读文件，每次调用之间再把范围收窄。Cursor 花成本养索引，换到的是白话查询也找得回东西。

编辑这边的分歧一样大。要讲清楚改了什么，有五种写法：

| 方案 | 模型送出什么 | 取舍 |
| --- | --- | --- |
| **diff 加 apply model** | 一份粗略的骨架 diff，再由第二个训练过的 model 改写。 | 快，也容错。但得多养一个 model。 |
| **旧字符串换新字符串** | 要找的原文，以及要换上去的文字。 | 没有歧义，错了会直接报错。前提是先读过文件。 |
| **行号** | 一段行号范围加上替换内容。 | 很省字。但前面一改，行号就过期。 |
| **编辑器命令** | 一套小型命令语言，vim 那种。 | 很精简。但又多一套语法可以写错。 |
| **锚点** | 一个起点标记加一个终点标记。 | 文件位移也不怕。但标记重复时会有歧义。 |

Claude Code 走的是精确的旧字符串替换，而且写之前一定要先读，所以对不上就是一个看得见的错误，不会变成一次改错的编辑。
Cursor 只送骨架，交给训练过的 apply model 把文件重写一遍，这样比叫模型吐出一份精准的 patch 还快。

### Running calls: early start and shell state

能重叠的不只是批次。一个调用只要自己的参数解析完就可以先跑起来，这时模型还在生成同一批的其他调用。
延迟就这样藏进生成里了，但要配一条失败规则：出错只中止那些依赖它的调用，不动同一批里互不相干的调用，也不动整个 turn。
这一层还有另一个要决定的：shell 状态。两种答案都站得住脚。

- **每次调用都重置：**Claude Code 的 bash 工具不会在调用之间留着一个活的 shell。这次设的环境变量和 shell function，下一次就没了，
  工具描述也直接叫模型用绝对路径。好处是每个调用自己就能重现，并行调用之间也不会互相污染。
- **共用一个常驻 session：**书里把共用一个终端当成默认，`cd`、export 出去的变量、启用中的虚拟环境都留得住。
  要并行做事时另外开隔离的 shell 就好。这样模型少打很多重复的设置命令，代价是 harness 多了一份状态要跟踪和重置。

### Discovery at scale

目录一大就不可能整份送出去。registry 先公告名称，完整 schema 等人要了才加载。而这个请求可以由模型自己用白话提出来：
MCP-Zero 让 agent 用自然语言说出自己缺哪一种能力，系统先配对到 server、再配对到工具，最后只把配到的那份 schema 注入进去。
模型不必事先知道某个工具存在也能开口要，这是关键字搜索做不到的。
注入还得对 cache 友好。把找到的 schema 附在 context 最后面一次，然后就别再动它。改动前缀那块工具定义，
它后面每一个 token 的 KV cache 都会失效（第 8 章）。用附加的方式，前缀保持原样，那份 schema 到了下一轮就是普通的历史记录。

---

## 各系统做法

各个 agent 如何定义工具、路由调用、处理并行，以及公开一份庞大目录。

| | Claude Code | mini-swe-agent |
| --- | --- | --- |
| **Pros** | 每个工具各自带验证、权限、安全并行和延迟探索。 | 单一 `bash` 工具小得多，也没有目录要维护。 |
| **Cons** | 每个工具都得背一份契约。 | 验证和权限做不到 per-tool。跑命令前的确认（第 3 章）看到的只有一条命令字符串。 |
| **Why** | 新增一项能力，应该就只是注册一个工具，loop 维持不变。 | 假设每个行动都能写成一条 shell 命令，所以一个工具就够了。 |
| **How: tool definition** | schema、handler 与判定式。 | 一份写死的 `bash` schema 就是整份目录，只有一个命令字段，别的名称一律报错。 |
| **How: dispatch** | 依名称查表，含别名。工具池依权限筛选，并合并 MCP 工具。 | 没有 registry，每次调用都是一条 shell 命令。 |
| **How: parallel calls** | 安全调用批量执行，不安全的单独执行。安全标记默认关闭。 | 没有。旧版文本模式每次响应只允许一个 action。 |
| **How: discovery** | 先给名称。完整 schema 依精确名称或关键字按需加载。 | 只有一个工具，不需要。 |

---

## 哪里会出错

- **未知的工具名称：**模型指名了一个不存在或已停用的工具。返回一个 `tool_result` 错误，而不是让 loop 崩溃。
- **schema 漂移：**schema 说一套，handler 期待另一套。在 dispatch 前先验证。
- **不安全的并行：**两个写入可能损毁同一个文件。默认采用顺序执行，除非确知某工具是安全的。
- **目录 overflow：**太多工具 schema 会挤爆 prompt。把完整 schema 延后到需要时再给，加载时附在最后面，让缓存住的前缀不受影响。
- **结果过大：**庞大的输出可能塞满 context window。限制结果大小、保存完整输出，并返回一段预览加一个路径。
  截断要标出来。默默截掉，模型就会拿一份残缺的文件当完整的在推理。
- **挑错工具：**两份 description 重叠，或一个工具身兼两职。把重复的合并、把过载的 schema 拆开，并在每份 description 里讲明这个工具不做什么。
- **input 被偷偷改掉：**harness 在送进 handler 的路上做了规范化，或多塞了一个参数。调用失败了，模型却查不出原因。输入不合法就带着理由拒绝。
- **失败扩散整批：**并行批次里有一个调用失败，整个 turn 就跟着死。只中止依赖它的那些调用。

---

## 可执行程序

[`src/`](src/) 承接 01 往前走，并加上：

- [`tools.py`](src/tools.py)：`Tool`、`Registry` 与 `run_concurrently`。
- [`loop.py`](src/loop.py)：把每个 `tool_use` 通过 `Registry` dispatch。
- [`demo.py`](src/demo.py)：注册一个 `ReadFile` 工具，并对着 API 执行 loop。
- [`test.py`](src/test.py)：检查 dispatch、未知工具错误与并行批次。

```bash
python sections/02-tool-runtime/src/test.py         # offline checks, no key
uv run python sections/02-tool-runtime/src/demo.py  # live demo, needs a key
```

---

## 出处

- [Claude Code source](https://github.com/yasasbanukaofficial/claude-code)：
  `Tool.ts`、`tools.ts`、`services/tools/toolOrchestration.ts`、`services/tools/toolExecution.ts`、`tools/ToolSearchTool/ToolSearchTool.ts`。
- [mini-swe-agent source](https://github.com/swe-agent/mini-swe-agent)：`models/utils/actions_toolcall.py`、`models/utils/actions_text.py`、`environments/__init__.py`。
- [learn-claude-code · s02_tool_use](https://github.com/shareAI-lab/learn-claude-code)：章节框架。
- [ai-agent-book](https://github.com/bojieli/ai-agent-book)：`book/chapter4.md`、`book/chapter5.md`（《深入理解 AI Agent》，李博杰；以中文原版为准）：
  五类工具的分法、粒度、description 的写法、参数保真、感知工具的接口规则、主动发现、对 cache 友好的加载、
  流式提前启动与只中止依赖项、常驻 shell 默认、搜索与编辑的比较，以及检查用参数。
  书中对 Claude Code 和 Cursor 的判读来自作者自己读源码，而那些实现变动很快，当成当时的证据看就好。
- [MCP-Zero](https://arxiv.org/abs/2506.01056)（Fei 等人）：agent 自己说出缺哪种能力，配对先找 server、再找工具。
- [τ-bench](https://arxiv.org/abs/2406.12045)（Sierra）：成绩看数据库的终态，检查用参数靠的就是这个。
