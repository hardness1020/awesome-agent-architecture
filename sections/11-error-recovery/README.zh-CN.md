# 11 · Error recovery

[English](README.md) · [繁體中文](README.zh-TW.md) · **简体中文**

> 先分类失败，再重试、调整，或停止。

一次 agent 执行可能横跨很多次模型调用。任何一次调用都可能因为网络问题、过载、rate limit、输出上限或 context overflow 而失败。

模型调用只是其中一层。有人研究了生产环境的 coding agent，把失败分成四层：API、tool、context、control flow。
API 层是 timeout、rate limit 和过载。tool 层是命令返回非零，或 handler 抛出异常。
context 层是 prompt overflow 和坏掉的消息历史。control flow 层是一直重复、却没有任何进展的步骤。
先判断是哪一层，再开始数次数。计数器要是在分类之前就跑起来，预算就会花在重试根本救不了的错误上。

loop 对不同的失败需要不同的响应：

1. 对暂时性错误重试。
2. 当问题出在 prompt 或输出上限时，调整后再重试。
3. 当错误无法恢复时，停止。

没有恢复机制，一次暂时的 API 失败就能终结一项长时间的任务。

---

## 机制

![机制图](assets/11-error-recovery.png)

把模型调用包在一个重试辅助函数里。这个辅助函数先分类失败，再采取一个有界限的行动。

- 暂时性的状态码会退避后重试。
- prompt overflow 会执行一次压缩 callback，然后重试。
- 反复的过载可以触发 fallback model。
- 未知或不可重试的错误会被抛出。

### New: 分类、backoff 与 retry helper

```python
RETRY_STATUS = {408, 409, 429}                         # src/recovery.py; these plus any 5xx

def should_retry(status) -> bool:
    return status in RETRY_STATUS or (status is not None and 500 <= status < 600)

def retry_delay(attempt, retry_after=None) -> float:   # exponential backoff + jitter
    if retry_after is not None:
        return float(retry_after)
    base = min(BASE_DELAY * 2 ** (attempt - 1), MAX_DELAY)
    return base + base * 0.25 * random()
```

overflow 会在一般状态处理之前先检查。如果压缩能缩小 prompt，`prompt_too_long` 错误就是可恢复的。

```python
def _status(e):
    return getattr(e, "status_code", None)

def _is_overflow(e) -> bool:
    return getattr(e, "overflow", False) or "prompt is too long" in str(e).lower()
```

`with_retry` 持有每次尝试的状态：

```python
def with_retry(call, on_overflow=None, fallback_model=None,
               max_retries=DEFAULT_MAX_RETRIES, sleep=time.sleep):
    consecutive_529 = 0
    overflowed = False
    for attempt in range(1, max_retries + 2):
        try:
            return call()
        except Exception as e:
            if _is_overflow(e):
                if on_overflow is None or overflowed:
                    raise
                overflowed = True
                on_overflow()
                continue
            status = _status(e)
            if status is None:
                raise
            if status == 529:
                consecutive_529 += 1
                if fallback_model and consecutive_529 >= MAX_529_RETRIES:
                    raise FallbackTriggered(fallback_model)
            if attempt > max_retries or not should_retry(status):
                raise
            sleep(retry_delay(attempt, getattr(e, "retry_after", None)))
```

### 如何整合

loop 把它的模型调用包起来：

```python
response = recovery.with_retry(
    lambda: model(messages, registry, system),
    on_overflow=lambda: _reactive_trim(messages),
    fallback_model=fallback_model)
```

- Recovery 只包住模型调用。
- `_reactive_trim` 就地修改 `messages[]`，供一次 overflow 重试使用。
- 当 recovery 放弃时，错误会被浮现出来，而不是被藏起来。

### 模型调用以外的部分

上面这个 helper 只顾到 API 这一层。另外三层各自需要自己的检查。

**没有进展。** 每次 tool call 都用「名称加参数」做成一个 fingerprint。fingerprint 一直重复，就代表 agent 在做同一件事，而且什么也没学到。
步数上限最后也会拦下来，但那时预算已经烧完了。fingerprint 计数器几步之内就能发现，而且说得出是哪一次调用卡住。
每条恢复路径也各自配一个失败计数器，这样一直失败的那条路会自己跳闸，不用等到全局上限。

**没有活性。** connect timeout 看不到「连上了、然后就没声音」的 stream。旁边再跑一个 idle watchdog，时间窗内没有 token 进来就取消这次调用。
接着 retry helper 就把这次取消当成一般的暂时性失败来处理。

**历史坏掉。** 一轮中途 crash，可能留下一个没有对应 `tool_result` 的 `tool_use` block。下一次请求会卡在消息格式，而不是卡在工作本身。
发出之前先把成对关系修好。至于「修」是什么意思，得看这份 transcript 是拿来做什么的。
产品用的 harness 会塞一个 placeholder 结果，写明这次调用被中断，让执行继续下去。
拿来录训练数据的 harness 则拒绝修补，因为造一个假结果，等于教模型一个根本没发生过的步骤。

### 恢复要分级

恢复不是一个决定。要照调用方该看到多少来分级。

1. 安静重试。调用方只看得到最后的结果。
2. 降级后继续。返回一个缩水的结果，并说清楚少了什么。
3. 把失败浮现出来，附上试过哪些方法，让模型可以换一条路走。

前两级产生的错误要隔离起来。先押在 helper 里面，等恢复真的放弃了才放出去。
中间过程的错误一旦传到模型面前，模型会当成最终结果，可能因此重做一件其实已经成功的工作。

恢复也可能自己喂自己。错误路径上要是还会触发带副作用的逻辑（hook、摘要、通知），那就又去调用一次模型，然后又失败一次。
在错误路径上把那些逻辑关掉，另外带一个递归深度计数器，把漏网的链条切断。
后台调用则完全不重试。它们不在关键路径上，重试只会把主 loop 需要的额度花掉。

界限要照实际量到的失败来定，不是靠直觉。有一份执行记录显示，同一条恢复路径失败了三千多次，
这类 loop 一天大约吃掉二十五万次 API 调用。压缩试三次就停，这个界限就是这样量出来的。
这些数字只有单一来源，看的时候要当成某个实现在某一段时期的样子。

---

## 各系统做法

Recovery 包住模型调用。loop 主体维持不变。

| | Claude Code | mini-swe-agent |
| --- | --- | --- |
| **Pros** | 针对性的恢复路径救回的 run 比一概重试更多。 | 只有三条路径要维护。就算 crash，磁盘上也留有完整轨迹。 |
| **Cons** | 要维护的分支与界限更多。 | 救回的 run 较少。context overflow 直接中止，连续三次格式错误也会结束 run。 |
| **Why** | 一次暂时的 API 失败不该终结长任务。 | 只留三条路：暂时性错误就重试、格式错误还给模型、其余带着具名状态退出。 |
| **How: retry** | 带退避重试 429、408、409 和 5xx，`retry-after` 优先。 | tenacity 退避 4 到 60 秒，最多 10 次。救不回的错误直接跳过。 |
| **How: token handling** | 提高输出 token、在 `max_tokens` 停止后续写，或在 `prompt_too_long` 时压缩。 | 没有，context overflow 直接中止 run。 |
| **How: model fallback** | 反复过载（529）后改用 fallback。后台来源的 529 重试次数有限制。 | 没有。 |

---

## 哪里会出错

- **Retry storm：**许多 client 同时对过载重试会让负载更糟。限制重试次数并尊重 `retry-after`。
- **无限恢复：**提高上限、续写和压缩都可能无限 loop。为每条路径设界限。
- **overflow 无法缩小：**如果一次 reactive compaction 失败，就停止，而不是永无止境地压缩。
- **错误消失：**一个被吞掉的错误会让 transcript 少了结果。在恢复用尽之后，把失败浮现出来。
- **Stop hook 重播 API 错误：**对 API 错误消息略过 stop hook。
- **卡住了，却没有错误：**一直重复同一个调用不会抛出任何东西，重试路径一条也不会启动。数重复的 tool 加参数 fingerprint，把 loop 打断。
- **stream 静静停住：**连上之后就没声音的 stream，是过得了 connect timeout 的。跑一个 idle watchdog，直接取消这次调用。
- **修补污染了记录：**塞一个 placeholder `tool_result` 能让产品环境的执行活下去，但也记下了一个根本没跑过的步骤。transcript 要拿去当训练数据时就别修。
- **中间错误外泄：**恢复还没结束就先送出去的错误，会被当成最终结果，害人白做一轮工。先隔离起来，等恢复放弃了再说。

---

## 可执行程序

[`src/`](src/) 承接 10 并加入：

- [`recovery.py`](src/recovery.py)：重试分类、退避、overflow 处理，以及 fallback 触发。
- [`loop.py`](src/loop.py)：把它的模型调用包在 `with_retry` 里。
- [`test.py`](src/test.py)：用一个假的不稳定调用驱动每一条路径。
- [`demo.py`](src/demo.py)：在一次 live 执行中注入一次模拟过载。

```bash
python sections/11-error-recovery/src/test.py         # offline checks, no key
uv run python sections/11-error-recovery/src/demo.py  # live demo, needs a key
```

---

## 来源

- [Claude Code 源码](https://github.com/yasasbanukaofficial/claude-code)：
  `services/api/withRetry.ts`、`query.ts`、`services/api/claude.ts`、`services/api/errors.ts`、`query/tokenBudget.ts`、`utils/context.ts`。
- [mini-swe-agent source](https://github.com/swe-agent/mini-swe-agent)：
  `models/utils/retry.py`、`models/litellm_model.py`、`agents/default.py` 的 `run()` 与 `max_consecutive_format_errors`。
- [ai-agent-book · 第 5 章](https://github.com/bojieli/ai-agent-book/blob/main/book/chapter5.md)（《深入理解 AI Agent》，李博杰，以中文原版为准）：
  四层失败分类、用 tool 加参数做 loop fingerprint、idle watchdog、`tool_result` 成对修补以及产品与训练数据两套标准、
  分级恢复加错误隔离，还有防死亡螺旋的那几招。它的脚注 ch5-3 说这套分类来自对生产环境 agent 的研究（其中包含 Claude Code），
  也提醒实现变动很快。三千多次失败的那份记录、以及一天二十五万次调用这两个数字，是书中作者自己的生产数据，只有单一来源。
- [learn-claude-code · s11_error_recovery](https://github.com/shareAI-lab/learn-claude-code)：章节框架。
