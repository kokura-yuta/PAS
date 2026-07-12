# PAS - Personal AI System

PASは、一人ひとりを長期的に理解し、人生に寄り添うことを目指したAIアシスタントです。

普通のチャットだけで終わらず、会話履歴、長期記憶、プロフィール、目標、AIの性格設定を使って、ユーザーを継続的に支援することを目指しています。

## 公開URL

https://personal-ai-system.onrender.com

Renderの無料プランを利用しているため、初回アクセス時に起動まで少し時間がかかる場合があります。

## 現在のバージョン

PAS v1.3 foundation

- v1.0: AIチャット、長期記憶、プロフィール、目標管理、性格設定、スマホ対応、Render公開
- v1.0.1: README整理、軽いUI修正、短文チャット時の速度改善
- v1.1: 日記チャット、自由チャット、ログイン、新規登録、ユーザーごとのデータ分離
- v1.2: Core Memoryの重要度・確信度・情報源・確認状態の管理
- v1.3 foundation: Timeline Memory、PAS Calendar、予定の作成・編集・削除

## 現在できること

- FastAPIでWebアプリを起動
- ホーム画面の表示
- AIチャット
- OpenAI APIを使った返答生成
- PostgreSQLへの会話保存
- 直近の会話履歴を使った返答
- 長期記憶の保存・表示・削除
- 長期記憶の確認待ち・確定・編集
- プロフィール保存
- 目標管理
- ログイン・新規登録
- ユーザーごとのデータ分離
- 日記チャット
- 自由チャット作成
- Timeline Memory
- PAS Calendar
- PAS内での予定作成・編集・削除
- AIの性格選択
- 返答の長さ設定
- テーマカラー切り替え
- LINE風チャットUI
- スマホ対応CSS
- 短いメッセージでは記憶抽出を省略し、返答速度を改善

## 使用技術

- Python 3.13
- FastAPI
- Jinja2
- HTML
- CSS
- OpenAI API
- SQLAlchemy
- PostgreSQL
- Render

## ローカル起動

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## 必要な環境変数

`.env` またはRenderのEnvironment Variablesに以下を設定します。

```text
OPENAI_API_KEY=your_openai_api_key
DATABASE_URL=your_postgresql_url
SESSION_SECRET_KEY=your_session_secret_key
APP_TIMEZONE=Asia/Tokyo
```

## Render設定

RenderでWeb Serviceを作成するときは、以下を設定します。

```text
Build Command:
pip install -r requirements.txt

Start Command:
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Pythonのバージョンは `.python-version` で `3.13` を指定しています。

## ロードマップ

- v1.4 AIコーチング
  - すぐ答えを出すだけでなく、必要な時に質問する
  - 悩みの真因を仮説として扱う
  - 共感、質問、提案の流れを強化する
- v1.5 Work PAS
  - 就活、面接、ES、SPI、キャリア設計を支援する
  - Core Memory、Timeline Memory、目標、予定を使って回答する
- v1.6 Event Coach AI
  - イベント前日の声かけ
  - イベント当日の応援
  - イベント終了後の振り返り
  - 振り返りをTimeline Memoryへ保存
  - イベントごとの通知ON/OFFと通知時間設定
- v1.7 Goal Planner AI
  - 目標から逆算してタスクへ分解する
  - 優先順位、期限、必要時間を管理する
  - PAS Calendarへの自動配置を目指す
  - 遅延検知、再計画、週間レビュー、月間レビューを行う
- v1.8 Specialist PAS
  - Work PAS、Study PAS、Fitness PAS、Mental PAS、Finance PASなどを追加する
  - すべての専門AIがCore MemoryとTimeline Memoryを共有する
- v1.9 専門AIの自動切り替え
  - 相談内容に応じて適切な専門AIを選ぶ
  - 必要に応じて複数の専門AIを組み合わせる
- v2.0 プロアクティブAI・人生OS化
  - AI Daily Check-in
  - 日記未記入時の声かけ
  - 目標進捗確認
  - イベント前後の声かけ
  - 感情変化やライフイベントに合わせた振り返り提案
  - 「質問に答えるAI」から「人生を伴走するAI」へ進化させる
