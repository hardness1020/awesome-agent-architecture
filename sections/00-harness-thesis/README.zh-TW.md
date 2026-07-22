# 0 · Harness thesis

[English](README.md) · **繁體中文** · [简体中文](README.zh-CN.md)

> 模型決定要做什麼。harness 提供工具、狀態與限制。

模型負責推理、選擇工具，以及何時停止。harness（外層架構）則是模型周圍的程式碼：loop、tool、memory、permission 與各種 interface。

單獨一次模型呼叫，只是對單一輸入產生一次回應。它可以決定要行動，卻無法自行行動。它沒有持久狀態、沒有工具執行器、無法存取檔案，也沒有權限關卡。

harness 必須：

1. 給行動一個執行的地方。
2. 給模型有用的觀察結果。
3. 在副作用抵達真實世界前先加以把關。
4. 保存狀態，讓後續呼叫能承接先前的呼叫。

沒有 harness，模型只能回答。它無法執行工具、觀察結果，也無法在多次呼叫之間記住工作進度。

---

## 機制

![機制圖](assets/00-harness-thesis.png)

這一章講的是分工。中心是一個小小的模型呼叫，輸入由 harness 準備，輸出由 harness 接手。

判斷歸模型，環境歸 harness。

第 1 章的 loop 是核心控制流程。其他章節在它周圍加上輸入、檢查或狀態：

- 第 2 章加上 tool runtime 與 dispatch。
- 第 3 章加上 permission 與 sandbox。
- 第 4 章加上攔截生命週期事件的 hook。
- 第 8 章與第 9 章加上 context 管理與跨 session memory。
- 第 10 章在每一輪組出 system prompt。
- 後面的章節加上 task、background execution、scheduling 與 isolation。

這些部分不會取代 loop。它們把輸入送進 loop、為 loop 把關，或替 loop 保存狀態。

### Harness 不是越複雜越好

每一層 harness，都是在補當下模型做不到的事。這讓每一層都帶著兩個成本：

1. 程式碼變多，要維護的變多，會出 bug 的地方也變多。
2. 設計綁著某一代模型。新模型可能自己就會規劃、恢復、驗證，這時還硬套舊的補救方式，反而會拉低表現。

所以 harness engineering 不是只有加，也包含刪。模型換代時，重新評估每一層：還有幫助的留下，新模型自己就做得到的就刪掉。
怎麼量測，見第 20、21 章。mini-swe-agent 就是最極端的例子：幾乎沒有 harness，也就幾乎沒有東西需要重新評估。

---

## 各系統做法

哪些事讓模型決定，哪些事交給周圍的程式碼。

| | Claude Code | mini-swe-agent |
| --- | --- | --- |
| **Pros** | harness 帶來安全性、持久化、subagent，以及隨需載入的知識。 | 幾乎沒有 harness 程式碼，也就沒什麼要維護的。 |
| **Cons** | 程式碼大多集中在 harness，要維護的東西多，bug 也大多出在這裡。 | 除了執行 bash 之外的每一種能力，都得靠模型自己。 |
| **Why** | 模型呼叫無法自行行動，所以環境全由 harness 負責。 | 假設一個 bash 工具就夠了。hook、skill、memory 與 task 都刻意不存在。 |
| **How: model owns** | 判斷、選擇工具、決定停止。模型看得到工具名稱、schema 與結果。 | 判斷、怎麼改檔案、何時提交。 |
| **How: harness owns** | loop、tool、permission、hook、knowledge、task 與 coordination。 | 一個 loop、一個 bash tool、跑指令前先問過使用者，再加上步數與成本上限。 |
| **How: size signal** | 多數程式碼都落在模型呼叫之外。 | 整個 agent class 大約 150 行。 |

---

## 哪裡會出錯

- **把 harness 的行為歸功給模型：**權限檢查與錯誤復原是 harness 的行為。它們出錯時要修的是 harness。
- **把該由模型做的決定寫死：**僵硬的工具順序與寫死的規劃會和模型衝突。需要判斷時，就讓模型去決定。
- **harness 太少：**一個沒有工具、權限或 context 管理的 loop，會把模型停在聊天機器人的層次。補上缺少的那一層。
- **harness 太多：**每加一層就多一份要維護的程式碼，而且為舊模型設計的那一層，可能反過來拖住新模型。模型換代時重新評估，沒有幫助的就刪掉。
- **職責混在一起：**把權限邏輯塞進工具執行裡，會更難測試也更難替換。維持清楚的契約，例如 `Tool.ts` 與 `PreToolUse`。

---

## 出處

- [Claude Code source (`cc-src/src`)](https://github.com/yasasbanukaofficial/claude-code)：`QueryEngine.ts`、`query/`、`Tool.ts`、`tools/`、`hooks/`、`types/permissions.ts`。
- [mini-swe-agent source](https://github.com/swe-agent/mini-swe-agent)：`agents/default.py`、`environments/local.py`、`__init__.py` 裡的 protocol。
- [mini-swe-agent README](https://github.com/swe-agent/mini-swe-agent)：模型變強之後，harness 可以更小的理由。
- [learn-claude-code · s20_comprehensive](https://github.com/shareAI-lab/learn-claude-code)：章節框架。
