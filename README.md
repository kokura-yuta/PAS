# Study PAS

Study PASは、「一人ひとりを理解し、教え方が成長していく先生」を目指す学習特化AIです。

v1.0では教育だけに集中します。日記、人生相談、Goal Planner、Google Calendar、Healthなどは入れず、まず「勉強がしやすい先生」としての完成度を高めます。

## 公開URL

https://personal-ai-system.onrender.com

Renderの無料プランを利用している場合、初回アクセス時に起動まで少し時間がかかることがあります。

## 現在のバージョン

Study PAS v1.0 foundation

- 科目ごとのチャット作成
- 科目ごとの専門AI
- 優しい先生キャラクター
- 全科目で共有するMemory
- 学習日時、学習回数、連続学習日数の記録
- 会話からテスト日・提出期限を簡易的に抽出
- 画像アップロードによる教材読み取りの入口
- Reactフロントエンド
- FastAPI JSON API
- PostgreSQL保存
- ログイン・新規登録

## v1.0で作らないもの

- 日記
- 人生相談
- Goal Planner
- Google Calendar
- Health
- 感情分析
- 複数キャラクター
- 音声
- SNS
- 複雑なグラフ

## Study PASの設計思想

Study PASは「AI家庭教師」ではなく、「自分のことを覚えていて、自分に合わせて教え方が育つ先生」を目指します。

ユーザーが毎回、理解度や苦手分野を入力する必要はありません。会話の中から、AIが理解度、苦手、説明方法の好み、テスト日、提出期限を少しずつ整理します。

判断基準は次の1つです。

「この機能は先生としての体験を良くするか？」

体験を良くしない機能は、v1.0では入れません。

## 現在できること

- FastAPIでWebアプリを起動
- Reactによるホーム・チャット画面
- 勉強したい科目を追加
- 科目ごとのチャット保存
- OpenAI APIを使った返答生成
- PostgreSQLへの会話保存
- 直近の会話履歴を使った返答
- 長期記憶の保存・表示・削除
- 長期記憶の確認待ち・確定・編集
- ログイン・新規登録
- ユーザーごとのデータ分離
- 画像アップロードによる教材読み取り
- スマホ対応CSS

## 使用技術

- Python 3.13
- FastAPI
- React
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

## 今後のロードマップ

- Study PAS v1.1
  - 理解度推定を強化
  - 苦手分野の復習提案
  - 前回の続き提案
- Study PAS v1.2
  - 添削機能
  - 応用問題生成
  - 学習レポート
- Study PAS v1.3
  - PDF、Word、PowerPointなどの教材アップロード
  - テスト日から逆算した学習計画
- Health PAS v2.0
  - 教育AIとは別プロダクトとして開発
  - 食事、睡眠、運動、体調を記録し、病院で説明しやすくする
