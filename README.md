# PAS - Personal AI System

PASは、一人ひとりを長期的に理解し、人生に寄り添うことを目指したAIアシスタントです。

普通のチャットだけで終わらず、会話履歴、長期記憶、プロフィール、目標、AIの性格設定を使って、ユーザーを継続的に支援することを目指しています。

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

## 今後の予定

- Render本番公開
- 会話履歴画面の整理
- UIの改善
- 長期記憶の自動整理
- Timeline Memory
- AIコーチング
- Work PAS / Life PAS / Fitness PAS / Study PAS
