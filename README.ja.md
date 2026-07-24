<h1 align="center" style="margin-top: 0;">Awesome Agent Architecture</h1>

<p align="center">
  <strong>LLM を中心に現代の AI Agent がどのように構築されているかを学びます。</strong><br>
</p>

<p align="center">
  <a href="#セクション"><img src="https://img.shields.io/badge/Focus-Harness_Engineering-6e40c9?style=for-the-badge" alt="対象：ハーネスエンジニアリング"></a>
  <a href="#調査対象のシステム"><img src="https://img.shields.io/badge/Systems-3+-0a7bbb?style=for-the-badge" alt="システム"></a>
  <a href="#セクション"><img src="https://img.shields.io/badge/Sections-22-green?style=for-the-badge" alt="セクション"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="ライセンス"></a>
</p>

<p align="center">
  <img src="https://github.com/user-attachments/assets/472d8152-5e46-4e39-9f09-e77dcd07936a" alt="Awesome Agent Architecture">
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.zh-TW.md">繁體中文</a> · <a href="README.zh-CN.md">简体中文</a> · <a href="README.ja.md">日本語</a>
</p>

モデルは推論します。ハーネスはモデルに行動、状態、制約を与えます。
ツールの実行、呼び出しをまたぐ状態の保持、副作用の制御、ループの連携は、モデルの単一呼び出しだけでは実現できません。

このリポジトリでは、ループ、ツール、メモリ、権限、コンテキスト、タスク、インターフェースというハーネスの各要素をセクションごとに説明します。
一度学べば多くの Agent を読み解けます。コーディングツール、チャットアシスタント、自律ランナーの違いは、主にハーネスの選択にあるためです。

**目次：** [ループ](#エージェントループ) · [学習方法](#学習方法) · [システム](#調査対象のシステム) ·
[セクション](#セクション) · [構成](#リポジトリ構成) · [実行](#デモの実行)

---

## エージェントループ

![エージェントループ](assets/the-agent-loop.png)

ほとんどの Agent は、モデルを呼び出し、要求されたツールを実行し、結果を追加して、再びモデルを呼び出すという同じ制御フローを共有します。

ループ自体は小さなものです。エンジニアリングの大半はその周囲にあり、ツールの振り分け、副作用の制御、コンテキスト管理、状態の永続化、ほかのループとの連携を担います。

---

## 学習方法

各セクションは自己完結しており、共通する 4 つの観点を使用します。

1. **導入。** このレイヤーが解決する問題。
2. **仕組み。** 一般的な設計と制御フロー。
3. **システム別。** 実際のシステムにおける実装方法。
4. **失敗モード。** 何が壊れ、どう軽減するか。

このリポジトリから学ぶには：

- **セクションを順番に読んでください。各セクションは前のレイヤーを土台にしています**。
- 実行可能なセクションでは、`src/loop.py` を読んでから `demo.py` を実行します。
- あるセクションの `src/` と直前のセクションを比較します。その差分が、そのセクションで追加される 1 つの仕組みです。

---

## 調査対象のシステム

各システムは、以下のセクションで使用する具体的な実装例です。

| システム                 | 利用される理由                                                               | 読み取るポイント                        | セクション             | 調査バージョン |
| ---------------------- | ------------------------------------------------------------------------------- | ---------------------------------- | -------------------- | --------------- |
| **Claude Code**  | 最先端のコーディング Agent：実際のリポジトリでファイルを編集し、コマンドを実行し、変更を届けます。 | 完全なハーネス。ここから始める       | 0～21（すべて）        | v2.1.88         |
| **Hermes Agent** | 長期利用向けアシスタント：ユーザーを記憶し、ワークフローを学習し、どこでも動作します。            | メモリ、Skill、常時接続チャネル | 7、9、14、16、19、21 | v2026.7.1       |
| **mini-swe-agent** | 研究用ベースライン：1 つの bash ツール、約 150 行。 | 最小の完全なループ、予算、評価ハーネス | 0～3、8、10、11、20、21 | v2.4.5 |
| *（今後追加予定）*        |                                                                                 |                                    |                      |                 |

> OpenClaw や aider など、ほかのシステムも今後追加できます。

---

## セクション

基本ループから自律実行するハーネスまでを 8 つのレイヤーで扱います。各行は自己完結した解説にリンクしています。

![学習パス](assets/learning-path.png)

| #  | セクション                                                      | 問い                                           | 主な仕組み                                        |
| -- | ------------------------------------------------------------ | -------------------------------------------------- | ----------------------------------------------------- |
|    | **レイヤー 0 · 基礎**                             |                                                    |                                                       |
| 0  | [ハーネスの基本命題](sections/00-harness-thesis/)                 | エージェンシーはどこから生まれるか？                       | モデルとハーネス、行動、観察、権限  |
|    | **レイヤー 1 · コアループ**                               |                                                    |                                                       |
| 1  | [エージェントループ](sections/01-agent-loop/)                         | Agent はどのように動作を続けるか？                      | `messages[]`、ループ、`stop_reason`                 |
| 2  | [ツールランタイム](sections/02-tool-runtime/)                     | ツールはどのように呼び出され、振り分けられるか？                   | レジストリ、スキーマ、ディスパッチ、遅延検索          |
| 3  | [権限とサンドボックス](sections/03-permission-sandbox/)   | 副作用をどのように制御するか？                        | 権限モード、承認、サンドボックス               |
| 4  | [フック](sections/04-hooks/)                                   | 拡張機能をループへどのように接続するか？              | `PreToolUse`、`PostToolUse`、ライフサイクルイベント     |
|    | **レイヤー 2 · 複雑な作業**                            |                                                    |                                                       |
| 5  | [計画と Todo](sections/05-planning-todos/)           | 大きな作業をどのように分解するか？                        | Plan モード、Todo リスト、編集前の承認           |
| 6  | [サブ Agent](sections/06-subagents/)                           | サブ問題をどのように分離するか？                      | 新しい `messages[]`、委任、子ループ           |
| 7  | [Skill](sections/07-skills/)                                 | 能力を必要に応じてどのように読み込むか？             | `SKILL.md`、カタログ、段階的開示         |
| 8  | [コンテキスト管理](sections/08-context-management/)         | 長いセッションをコンテキストウィンドウにどう収めるか？               | 予算管理、スタブ、圧縮、要約               |
|    | **レイヤー 3 · 知識と回復力**                  |                                                    |                                                       |
| 9  | [メモリ](sections/09-memory/)                                 | 実行をまたいでどのように記憶するか？                  | 選択、想起、抽出、統合          |
| 10 | [システムプロンプトの組み立て](sections/10-system-prompt/)          | ターンごとにプロンプトをどのように構築するか？                 | プロンプトセクション、ライブ状態、キャッシュ境界         |
| 11 | [エラー回復](sections/11-error-recovery/)                 | 長時間タスクを障害からどう回復させるか？              | 再試行、オーバーフロー回復、フォールバックモデル            |
|    | **レイヤー 4 · 長時間実行と非同期**                    |                                                    |                                                       |
| 12 | [タスクシステム](sections/12-task-system/)                       | ターンを越えて作業をどのように永続化するか？               | タスクレコード、依存関係、ロック                     |
| 13 | [バックグラウンド実行](sections/13-background-execution/)     | メインループの外でどのように作業を実行するか？               | ハンドル、タスク状態、通知キュー               |
| 14 | [スケジューリング](sections/14-scheduling/)                         | Agent を後からどのように実行するか？                       | Cron、スリープ、リモートトリガー、キュー                  |
| 15 | [Worktree 分離](sections/15-worktree-isolation/)         | 並列作業の衝突をどう防ぐか？           | Git worktree、cwd の固定、安全なクリーンアップ              |
|    | **レイヤー 5 · マルチ Agent**                             |                                                    |                                                       |
| 16 | [連携](sections/16-coordination/)                     | 複数の Agent はどのように通信するか？                           | 受信箱、ブロードキャスト、権限のバブリング              |
| 17 | [プロトコル](sections/17-protocols/)                           | Agent 同士がどのように合意し、安全に停止するか？              | 計画の承認、シャットダウンハンドシェイク                    |
| 18 | [自律性](sections/18-autonomy/)                             | Agent はどのように自己組織化するか？                 | アイドルサイクル、タスクの取得、自己組織化          |
|    | **レイヤー 6 · 拡張と統合**                 |                                                    |                                                       |
| 19 | [MCP / プラグイン / チャネル](sections/19-mcp-plugins-channels/) | ハーネスはどのように外部世界へ到達するか？              | トランスポート、チャネル、ツールプールの組み立て              |
| 20 | [可観測性と評価](sections/20-observability/)  | 動作をどのように確認するか？                           | トレース、メトリクス、評価、障害分析             |
|    | **レイヤー 7 · 構成**                             |                                                    |                                                       |
| 21 | [ループエンジニアリング](sections/21-loop-engineering/)             | 自律実行するシステムへループをどのように積み重ねるか？ | 検証ループ、トリガー、予算、成熟度レベル |

---

## リポジトリ構成

`00-harness-thesis/` から `21-loop-engineering/` まで、22 のセクション解説がすべて揃っています。

```text
awesome-agent-architecture/
├── README.md                  # トップレベルの地図
├── sections/                  # セクションごとに 1 つのフォルダー
│   ├── 00-harness-thesis/     # セクションごとの README.md
│   ├── 01-agent-loop/src/     # 実行可能なチェーンはここから始まる
│   ├── ...
│   └── 21-loop-engineering/
└── references/                # 一次資料と先行事例
```

各セクションのフォルダーは `NN-name/` という形式で、`README.md` を含みます。

セクション 1～21 には、実行可能な `src/` もあります。コードはセクションごとに積み重なります。
各セクションは 1 つの仕組みを追加して `loop.py` を発展させるため、隣接するセクションの差分から変更点を確認できます。

---

## デモの実行

セクション 1～21 には実行可能なデモがあります。リポジトリのルートで一度セットアップします。

```bash
uv venv
uv pip install -r requirements.txt
cp .env.example .env        # その後 ANTHROPIC_API_KEY を追加
```

固定された依存関係は [`requirements.txt`](requirements.txt) にあります。`.env` は gitignore の対象で、次の値を保持します。

- `ANTHROPIC_API_KEY`
- 任意の `ANTHROPIC_MODEL`
- 任意の `ANTHROPIC_BASE_URL`

各実行可能セクションには以下があります。

- `test.py`：オフラインチェック。キーは不要です。
- `demo.py`：API を使用するライブデモ。

```bash
python sections/01-agent-loop/src/test.py         # オフライン
uv run python sections/01-agent-loop/src/demo.py  # ライブ
```

---

## コントリビューション

- **システムを追加する。** 同じセクション構造へ新しい Agent を組み込みます。
- **セクションを掘り下げる。** 仕組み、より明確な図、より的確な失敗モードを追加します。
- **記録を訂正する。** ここでの内容は、ソース、ドキュメント、動作から再構成したものです。出典を示した訂正を歓迎します。

推測ではなく、名前があり検証可能な仕組みを優先してください。出典を引用してください。

---

## 参考資料

- [claude-code](https://github.com/yasasbanukaofficial/claude-code)：仕組みの名称と実装パスに使用した Claude Code のソースバックアップ。
- [hermes-agent](https://github.com/NousResearch/hermes-agent)：2 番目の調査対象システムとして使用するオープンソースの Agent ハーネス（MIT）。
- [mini-swe-agent](https://github.com/swe-agent/mini-swe-agent)：3 番目の調査対象システムとして使用する最小 SWE Agent（MIT）。
- [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)：コード中心のハーネス再構成とセクション設計。
- [Anthropic Agent Skills best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)：Skill の段階的開示レベル。
- [Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)：キャッシュの区切り、TTL、料金、最小トークン数。
- [cobusgreyling/loop-engineering](https://github.com/cobusgreyling/loop-engineering)：ループの構成要素と準備度レベル。
- [LangChain · The art of loop engineering](https://www.langchain.com/blog/the-art-of-loop-engineering)：積み重ねられた 4 つのループ。
- [Addy Osmani · Loop engineering](https://addyosmani.com/blog/loop-engineering/)：Agent ループを構成する構成要素。
- [MindStudio · What is loop engineering](https://www.mindstudio.ai/blog/what-is-loop-engineering-autonomous-ai-agent-workflows)：自律ワークフローの目標条件。
- [Lilian Weng · Harness engineering for self-improvement](https://lilianweng.github.io/posts/2026-07-04-harness/)：ループ外のゲートを備えた改善ループ。
