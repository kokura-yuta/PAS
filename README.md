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
- ログイン前の利用規約・AI利用・年齢確認への同意
- 規約バージョンと同意日時の保存、重要改定時の再同意
- PWAとしてホーム画面へインストール

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

## プラン制限

- Free: AIチャット・AI授業、AI教科書3冊、AIロードマップ3つ
- Premium（月額800円）: AI教科書・AIロードマップ無制限
- 教科書・ロードマップは削除するとFreeプランの空き枠がすぐに戻ります
- Stripe Checkoutによる月額決済、Customer Portalによる請求・解約管理、署名検証済みWebhookによる権限同期に対応しています
- 決済開始時にStripeのPriceが「800 JPY・1か月ごと」であることをサーバー側でも検証します
- 購入直前に総額、自動更新、支払時期、提供時期、解約・返金条件を再確認します
- Stripe設定と特定商取引法上の販売者情報が揃うまで、新規Premium決済は自動的に無効になります

## 利用規約・プライバシー・販売表示

- `/consent`: ログイン・新規登録前の同意画面
- `/terms`: 利用規約
- `/privacy`: プライバシーポリシー
- `/commerce-disclosure`: 特定商取引法に基づく表示

規約にはAI回答の限界、禁止事項、Premiumの自動更新、解約・返金条件、サービス中断、責任制限を記載しています。全面免責や例外のない返金不可とはせず、消費者契約法その他の法令上制限できない責任と利用者の権利を除外しています。公開前に、日本のITサービス・消費者契約に詳しい弁護士へ事業者情報と実際の運用を含めた最終確認を依頼してください。

`TERMS_VERSION`を更新すると、既存ユーザーにも次回アクセス時に再同意を求めます。文言を変えた場合は、同時に`TERMS_EFFECTIVE_DATE`を更新してください。

## PWAアプリ

HTTPSで公開すると、対応ブラウザからStudy PASをホーム画面へ追加し、独立したアプリ画面として起動できます。認証後のHTML、API応答、チャットやMemoryはService Workerへキャッシュしません。オフライン時は接続案内だけを表示します。

App Store・Google Playへネイティブアプリとして申請する場合、アプリ内のデジタル機能販売には各ストアのアプリ内課金が必要になる場合があります。現在のStripe CheckoutはWeb/PWA向けです。ストア公開時は、各ストアの審査・課金要件に合わせて購入経路とサブスクリプション同期を別途実装してください。

## 使用技術

- Python 3.13
- FastAPI
- React
- Jinja2
- HTML
- CSS
- OpenAI API
- Stripe Billing
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
ENVIRONMENT=production
OPENAI_API_KEY=your_openai_api_key
DATABASE_URL=your_postgresql_url
SESSION_SECRET_KEY=32文字以上のランダムな秘密値
APP_BASE_URL=https://your-domain.example
APP_TIMEZONE=Asia/Tokyo
SMTP_HOST=your_smtp_host
SMTP_PORT=587
SMTP_FROM_EMAIL=no-reply@your-domain.example
AI_DAILY_REQUEST_LIMIT=100
STRIPE_SECRET_KEY=sk_live_your_stripe_secret_key
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret
STRIPE_PREMIUM_PRICE_ID=price_your_monthly_800_jpy_price
TERMS_VERSION=2026-07-20
PRIVACY_VERSION=2026-07-20
TERMS_EFFECTIVE_DATE=2026年7月20日
LEGAL_BUSINESS_NAME=販売事業者名
LEGAL_REPRESENTATIVE=運営責任者名
LEGAL_ADDRESS=事業者住所または適法な開示方法の表示
LEGAL_PHONE=電話番号または適法な開示方法の表示
LEGAL_EMAIL=support@your-domain.example
```

本番環境ではアプリ本体の必須設定が不足していると起動を停止します。Stripeの3項目または`LEGAL_`の5項目が未設定の場合、アプリは起動しますが新規Premium決済ボタンは無効になります。既存契約者の請求管理・解約導線は維持されます。Renderでは`RENDER`環境変数を検出して自動的に本番モードになります。

## Stripe Premium設定

1. Stripeで「Study PAS Premium」の商品を作り、通貨JPY、単価800円、請求期間「毎月」の継続Priceを作成します。
2. Price IDを`STRIPE_PREMIUM_PRICE_ID`へ設定します。
3. Webhook送信先を`https://your-domain.example/api/billing/webhook`として登録し、次のイベントを購読します。
   - `checkout.session.completed`
   - `checkout.session.async_payment_succeeded`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
4. Webhook署名シークレットを`STRIPE_WEBHOOK_SECRET`へ設定します。
5. Stripe Customer Portalを有効にして、利用者が支払い方法・請求・解約を管理できるようにします。
6. `LEGAL_`の5項目を実際の販売者情報で設定し、`/commerce-disclosure`の表示を確認します。

テスト環境では`sk_test_`とテスト用Webhook secret、公開時は`sk_live_`と本番用Webhook secretを組み合わせます。秘密鍵やWebhook secretは`.env`またはRenderのEnvironment Variablesにだけ保存し、Gitには追加しません。

## テスト

既存の仮想環境を使う場合:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

テストは一時SQLiteデータベースを使用し、実運用のデータベースには接続しません。認証、ユーザー間のデータ分離、レート制限、画像判定、セキュリティヘッダー、ヘルスチェックを確認します。

## 運用確認

- RenderのHealth Check Pathを`/health`に設定
- PostgreSQLの自動バックアップを有効化し、定期的に復元テストを実施
- ログの`request_id`を使って障害リクエストを追跡
- OpenAI側で月間利用上限と使用量通知を設定
- アプリ側の`AI_DAILY_REQUEST_LIMIT`を利用規模と予算に合わせて設定
- SMTP送信失敗をRenderログまたは外部監視で通知
- デプロイ前に自動テストを実行

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
