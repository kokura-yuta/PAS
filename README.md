# PAS - Personal AI System

PASは、一人ひとりを長期的に理解し、人生に寄り添うことを目指したAIアシスタントです。

普通のチャットだけで終わらず、会話履歴、長期記憶、プロフィール、目標、AIの性格設定を使って、ユーザーを継続的に支援することを目指しています。

## 公開URL

https://personal-ai-system.onrender.com

Renderの無料プランを利用しているため、初回アクセス時に起動まで少し時間がかかる場合があります。

## 現在のバージョン

PAS v1.0.1

- v1.0: AIチャット、長期記憶、プロフィール、目標管理、性格設定、スマホ対応、Render公開
- v1.0.1: README整理、軽いUI修正、短文チャット時の速度改善

## 現在できること

- FastAPIでWebアプリを起動
- ホーム画面の表示
- AIチャット
- OpenAI APIを使った返答生成
- PostgreSQLへの会話保存
- 直近の会話履歴を使った返答
- 長期記憶の保存・表示・削除
- プロフィール保存
- 目標管理
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

- v1.1 Chat Threads
  - 日記チャットを用意する
  - ユーザーが自由にチャットを作成できるようにする
  - 話題ごとに会話履歴を分ける
- v1.2 Core Memory強化
  - 重要情報の自動抽出を改善
  - 記憶の重要度・確信度を管理
  - AIの推測と本人発言を区別
- v1.3 Timeline Memory
  - 過去・現在・未来の出来事を整理
  - 人生の流れとして記憶を扱う
- v1.4 AIコーチング
  - 質問を通じた自己理解支援
  - 悩みの真因分析
- v1.5 Work PAS
  - 就活・キャリア支援に特化
- v2.0
  - 外部サービス連携
  - 成長分析
  - 複数ユーザー対応
  - サービス化準備
