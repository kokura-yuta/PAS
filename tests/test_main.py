import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["SESSION_SECRET_KEY"] = "test-session-secret-only"
os.environ["ENVIRONMENT"] = "test"

from fastapi.testclient import TestClient

import main


class StudyPasTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        main.engine.dispose()
        os.unlink(database_file.name)

    def setUp(self):
        main.rate_limiter.events.clear()
        for name in (
            "STRIPE_SECRET_KEY",
            "STRIPE_WEBHOOK_SECRET",
            "STRIPE_PREMIUM_PRICE_ID",
            "LEGAL_BUSINESS_NAME",
            "LEGAL_REPRESENTATIVE",
            "LEGAL_ADDRESS",
            "LEGAL_PHONE",
            "LEGAL_EMAIL"
        ):
            os.environ.pop(name, None)
        with main.SessionLocal() as db:
            for table in reversed(main.Base.metadata.sorted_tables):
                db.execute(table.delete())
            db.commit()
        self.client.cookies.clear()

    def signup(self, name="テスト", email="test@example.com", password="password123"):
        self.accept_consent("/signup")
        return self.client.post(
            "/signup",
            data={"name": name, "email": email, "password": password},
            follow_redirects=False
        )

    def accept_consent(self, next_path="/login"):
        return self.client.post(
            "/consent",
            data={
                "next": next_path,
                "accept_terms": "on",
                "accept_ai_notice": "on",
                "accept_age": "on"
            },
            follow_redirects=False
        )

    def configure_stripe(self):
        os.environ["STRIPE_SECRET_KEY"] = "sk_test_unit"
        os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_unit"
        os.environ["STRIPE_PREMIUM_PRICE_ID"] = "price_monthly_800"
        os.environ["LEGAL_BUSINESS_NAME"] = "テスト事業者"
        os.environ["LEGAL_REPRESENTATIVE"] = "テスト責任者"
        os.environ["LEGAL_ADDRESS"] = "東京都テスト"
        os.environ["LEGAL_PHONE"] = "000-0000-0000"
        os.environ["LEGAL_EMAIL"] = "legal@example.com"

    def fake_stripe_client(
        self,
        price=None,
        checkout_session=None,
        subscription=None,
        portal_session=None,
        event=None
    ):
        price = price or {
            "id": "price_monthly_800",
            "active": True,
            "currency": "jpy",
            "unit_amount": 800,
            "recurring": {"interval": "month", "interval_count": 1}
        }
        checkout_session = checkout_session or {
            "id": "cs_test_unit",
            "url": "https://checkout.stripe.com/c/pay/test"
        }
        subscription = subscription or {
            "id": "sub_unit",
            "customer": "cus_unit",
            "status": "active",
            "metadata": {}
        }
        portal_session = portal_session or {
            "url": "https://billing.stripe.com/p/session/test"
        }
        client = SimpleNamespace(
            construct_event=Mock(return_value=event or {}),
            v1=SimpleNamespace(
                prices=SimpleNamespace(
                    retrieve=Mock(return_value=price)
                ),
                checkout=SimpleNamespace(
                    sessions=SimpleNamespace(
                        create=Mock(return_value=checkout_session),
                        retrieve=Mock(return_value=checkout_session)
                    )
                ),
                subscriptions=SimpleNamespace(
                    retrieve=Mock(return_value=subscription),
                    cancel=Mock(return_value=subscription)
                ),
                billing_portal=SimpleNamespace(
                    sessions=SimpleNamespace(
                        create=Mock(return_value=portal_session)
                    )
                )
            )
        )
        return client

    def test_health_and_security_headers(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.assertTrue(response.headers["x-request-id"])

    def test_pwa_manifest_and_service_worker_are_available(self):
        manifest_response = self.client.get("/static/manifest.webmanifest")
        self.assertEqual(manifest_response.status_code, 200)
        manifest = manifest_response.json()
        self.assertEqual(manifest["name"], "Study PAS")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(
            {icon["sizes"] for icon in manifest["icons"]},
            {"192x192", "512x512"}
        )

        worker_response = self.client.get("/service-worker.js")
        self.assertEqual(worker_response.status_code, 200)
        self.assertEqual(worker_response.headers["service-worker-allowed"], "/")
        self.assertIn("no-store", worker_response.headers["cache-control"])
        self.assertIn('request.mode === "navigate"', worker_response.text)
        self.assertNotIn("/api/home", worker_response.text)

    def test_signup_login_logout_flow(self):
        response = self.signup()
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.client.get("/api/home").status_code, 200)

        response = self.client.post("/logout", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.client.get("/api/home").status_code, 401)

        self.accept_consent("/login")
        response = self.client.post(
            "/login",
            data={"email": "test@example.com", "password": "wrong"}
        )
        self.assertIn("メールアドレスかパスワードが違います", response.text)

    def test_user_cannot_read_another_users_thread(self):
        self.signup(name="利用者A", email="a@example.com")
        created = self.client.post("/api/chat_threads", json={"title": "数学"})
        self.assertEqual(created.status_code, 200)
        thread_id = created.json()["thread"]["id"]
        self.client.post("/logout")

        self.signup(name="利用者B", email="b@example.com")
        response = self.client.get(f"/api/chat/{thread_id}")
        self.assertEqual(response.status_code, 404)

    def test_empty_message_is_rejected(self):
        self.signup()
        created = self.client.post("/api/chat_threads", json={"title": "英語"})
        thread_id = created.json()["thread"]["id"]
        response = self.client.post(f"/api/chat/{thread_id}/messages", json={"message": "   "})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "message_required")

    def test_rate_limiter_blocks_after_limit(self):
        limiter = main.SlidingWindowRateLimiter()
        self.assertEqual(limiter.allow("login:test", 2, 60), (True, 0))
        self.assertEqual(limiter.allow("login:test", 2, 60), (True, 0))
        allowed, retry_after = limiter.allow("login:test", 2, 60)
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry_after, 1)

    def test_cross_site_write_is_rejected(self):
        response = self.client.post(
            "/login",
            data={"email": "test@example.com", "password": "password123"},
            headers={"Origin": "https://attacker.example"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "cross_site_request_rejected")

    def test_password_hash_supports_new_and_legacy_format(self):
        password = "password123"
        new_hash = main.hash_password(password)
        self.assertTrue(main.verify_password(password, new_hash))

        salt = "legacy-salt"
        legacy_hash = main.hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), 120000
        ).hex()
        self.assertTrue(main.verify_password(password, f"{salt}${legacy_hash}"))

    def test_image_signature_validation(self):
        self.assertEqual(main.detect_supported_image_type(b"\x89PNG\r\n\x1a\nrest"), "image/png")
        self.assertEqual(main.detect_supported_image_type(b"\xff\xd8\xffrest"), "image/jpeg")
        self.assertIsNone(main.detect_supported_image_type(b"not-an-image"))

    def test_export_contains_only_current_users_data(self):
        self.signup(name="利用者A", email="a@example.com")
        self.client.post("/api/chat_threads", json={"title": "数学"})
        response = self.client.get("/account/export")
        self.assertEqual(response.status_code, 200)
        exported = response.json()
        self.assertEqual(exported["account"]["email"], "a@example.com")
        self.assertNotIn("password_hash", exported["account"])
        self.assertEqual(len(exported["data"]["chat_threads"]), 1)
        self.assertIn("attachment", response.headers["content-disposition"])

    def test_account_delete_removes_account_and_related_data(self):
        self.signup()
        self.client.post("/api/chat_threads", json={"title": "数学"})
        response = self.client.post(
            "/account/delete",
            data={"password": "password123"},
            follow_redirects=False
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.client.get("/api/home").status_code, 401)
        with main.SessionLocal() as db:
            self.assertEqual(db.query(main.User).count(), 0)
            self.assertEqual(db.query(main.ChatThread).count(), 0)

    def test_daily_ai_limit_blocks_before_generation(self):
        self.signup()
        created = self.client.post("/api/chat_threads", json={"title": "数学"})
        thread_id = created.json()["thread"]["id"]
        with main.SessionLocal() as db:
            user = db.query(main.User).first()
            db.add(main.ChatMessage(user_id=user.id, thread_id=thread_id, role="user", content="既存"))
            db.commit()

        original_limit = main.AI_DAILY_REQUEST_LIMIT
        main.AI_DAILY_REQUEST_LIMIT = 1
        try:
            response = self.client.post(
                f"/api/chat/{thread_id}/messages",
                json={"message": "新しい質問"}
            )
        finally:
            main.AI_DAILY_REQUEST_LIMIT = original_limit

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error"], "daily_ai_limit_reached")

    def test_failed_ai_does_not_count_as_study_and_retry_does_not_duplicate_user(self):
        self.signup()
        created = self.client.post("/api/chat_threads", json={"title": "世界史"})
        thread_id = created.json()["thread"]["id"]
        with main.SessionLocal() as db:
            user = db.query(main.User).first()
            user_id = user.id

        thread = main.load_chat_thread(thread_id, user_id)
        original_client = main.client

        class FailingResponses:
            def create(self, **kwargs):
                raise RuntimeError("test failure")

        class FailingClient:
            responses = FailingResponses()

        main.client = FailingClient()
        try:
            main.process_chat_message(thread, user_id, "短い質問")
        finally:
            main.client = original_client

        failed_thread = main.load_chat_thread(thread_id, user_id)
        self.assertEqual(failed_thread.study_session_count, 0)

        with main.SessionLocal() as db:
            self.assertEqual(
                db.query(main.ChatMessage).filter(main.ChatMessage.user_id == user_id).filter(main.ChatMessage.role == "user").count(),
                1
            )
            self.assertEqual(
                db.query(main.ChatMessage).filter(main.ChatMessage.user_id == user_id).filter(main.ChatMessage.role == "assistant").count(),
                0
            )

        class SuccessfulResponse:
            output_text = "短い説明です。"

        class SuccessfulResponses:
            def create(self, **kwargs):
                return SuccessfulResponse()

        class SuccessfulClient:
            responses = SuccessfulResponses()

        main.client = SuccessfulClient()
        try:
            main.process_chat_message(thread, user_id, "短い質問", retry_last=True)
        finally:
            main.client = original_client

        successful_thread = main.load_chat_thread(thread_id, user_id)
        self.assertEqual(successful_thread.study_session_count, 1)
        with main.SessionLocal() as db:
            self.assertEqual(
                db.query(main.ChatMessage).filter(main.ChatMessage.user_id == user_id).filter(main.ChatMessage.role == "user").count(),
                1
            )
            self.assertEqual(
                db.query(main.ChatMessage).filter(main.ChatMessage.user_id == user_id).filter(main.ChatMessage.role == "assistant").count(),
                1
            )

    def test_auth_forms_have_accessible_labels_and_password_hint(self):
        self.accept_consent("/signup")
        signup = self.client.get("/signup")
        self.assertEqual(signup.status_code, 200)
        self.assertIn('for="signup-name"', signup.text)
        self.assertIn('id="signup-name"', signup.text)
        self.assertIn('for="signup-email"', signup.text)
        self.assertIn('for="signup-password"', signup.text)
        self.assertIn("8文字以上で設定してください", signup.text)

        login = self.client.get("/login")
        self.assertEqual(login.status_code, 200)
        self.assertIn('for="login-email"', login.text)
        self.assertIn('for="login-password"', login.text)

    def test_login_and_signup_require_explicit_consent_first(self):
        login = self.client.get("/login", follow_redirects=False)
        self.assertEqual(login.status_code, 303)
        self.assertIn("/consent?next=", login.headers["location"])

        consent = self.client.get("/consent?next=/login")
        self.assertEqual(consent.status_code, 200)
        self.assertIn("利用前の大切な確認", consent.text)
        self.assertIn("利用規約", consent.text)
        self.assertIn("プライバシーポリシー", consent.text)

        incomplete = self.client.post(
            "/consent",
            data={"next": "/login", "accept_terms": "on"},
            follow_redirects=False
        )
        self.assertEqual(incomplete.status_code, 400)

        accepted = self.accept_consent("/login")
        self.assertEqual(accepted.status_code, 303)
        self.assertEqual(accepted.headers["location"], "/login")
        self.assertEqual(self.client.get("/login").status_code, 200)

    def test_terms_version_and_acceptance_time_are_saved(self):
        self.signup()
        with main.SessionLocal() as db:
            user = db.query(main.User).first()
            self.assertEqual(user.terms_version, main.TERMS_VERSION)
            self.assertEqual(user.privacy_version, main.PRIVACY_VERSION)
            self.assertIsNotNone(user.terms_accepted_at)
            records = db.query(main.ConsentRecord).filter(main.ConsentRecord.user_id == user.id).all()
            self.assertEqual(len(records), 1)
            self.assertTrue(records[0].ai_notice_accepted)
            self.assertTrue(records[0].age_confirmed)
            self.assertEqual(records[0].acceptance_source, "signup")

        exported = self.client.get("/account/export").json()
        self.assertEqual(exported["account"]["terms_version"], main.TERMS_VERSION)
        self.assertEqual(exported["account"]["privacy_version"], main.PRIVACY_VERSION)
        self.assertTrue(exported["account"]["terms_accepted_at"])
        self.assertEqual(len(exported["data"]["consent_records"]), 1)

    def test_terms_or_privacy_version_change_requires_reconsent(self):
        self.signup()

        with patch.object(main, "PRIVACY_VERSION", "2026-07-21"):
            self.assertEqual(self.client.get("/api/home").status_code, 401)
            redirect = self.client.get("/login", follow_redirects=False)
            self.assertEqual(redirect.status_code, 303)
            self.assertIn("/consent", redirect.headers["location"])

            accepted = self.accept_consent("/")
            self.assertEqual(accepted.status_code, 303)
            self.assertEqual(self.client.get("/api/home").status_code, 200)

            with main.SessionLocal() as db:
                user = db.query(main.User).first()
                self.assertEqual(user.privacy_version, "2026-07-21")
                records = db.query(main.ConsentRecord).filter(main.ConsentRecord.user_id == user.id).all()
                self.assertEqual(len(records), 2)

    def test_settings_are_fixed_to_study_pas_style(self):
        self.signup()
        with main.SessionLocal() as db:
            settings = db.query(main.Settings).first()
            settings.default_persona = "mentor"
            settings.theme_name = "deep"
            db.commit()

        page = self.client.get("/settings")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn("メンター", page.text)
        self.assertNotIn("テーマ", page.text)
        self.assertIn("優しい先生に統一されています", page.text)

        response = self.client.post(
            "/settings",
            data={
                "response_length": "concise",
                "default_persona": "strict_teacher",
                "theme_name": "warm"
            },
            follow_redirects=False
        )
        self.assertEqual(response.status_code, 303)
        with main.SessionLocal() as db:
            settings = db.query(main.Settings).first()
            self.assertEqual(settings.default_persona, "friend")
            self.assertEqual(settings.theme_name, "calm")
            self.assertEqual(settings.response_length, "concise")

    def test_memory_page_uses_study_labels_without_internal_scores(self):
        self.signup()
        with main.SessionLocal() as db:
            user = db.query(main.User).first()
            db.add(main.Memory(
                user_id=user.id,
                category="weak_area",
                content="分数の通分でつまずきやすい",
                importance=5,
                confidence=0.75,
                source_type="ai_inference",
                status="confirmed",
                is_active=True
            ))
            db.commit()

        response = self.client.get("/memories")
        self.assertEqual(response.status_code, 200)
        self.assertIn("先生が覚えていること", response.text)
        self.assertIn("苦手・つまずき", response.text)
        self.assertIn("分数の通分でつまずきやすい", response.text)
        self.assertNotIn("確信度:", response.text)
        self.assertNotIn("重要度:", response.text)

    def test_free_textbook_limit_blocks_fourth_and_delete_reopens_slot(self):
        self.signup()
        created = self.client.post("/api/chat_threads", json={"title": "数学"})
        thread_id = created.json()["thread"]["id"]

        with main.SessionLocal() as db:
            user = db.query(main.User).first()
            user_id = user.id
            for index in range(3):
                db.add(main.StudyTextbook(
                    user_id=user_id,
                    thread_id=thread_id,
                    subject=f"科目{index}",
                    title=f"教科書{index}"
                ))
            db.commit()

        response = self.client.post(
            f"/api/chat/{thread_id}/textbook_preview",
            json={"source_note": "新しい教科書"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "textbook_limit_reached")
        self.assertEqual(response.json()["message"], "無料プランでは教科書は3冊までです。")

        with main.SessionLocal() as db:
            textbook_id = db.query(main.StudyTextbook).order_by(main.StudyTextbook.id.asc()).first().id

        deleted = self.client.delete(f"/api/textbooks/{textbook_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["plan_usage"]["textbooks"]["used"], 2)
        self.assertFalse(deleted.json()["plan_usage"]["textbooks"]["reached"])

        saved = self.client.post(
            "/api/textbooks/confirm",
            json={
                "thread_id": thread_id,
                "mode": "create",
                "title": "新しい教科書",
                "bookshelf_subject": "数学",
                "basic_explanation": "新しい説明"
            }
        )
        self.assertEqual(saved.status_code, 200)

        blocked_again = self.client.post(
            "/api/textbooks/confirm",
            json={
                "thread_id": thread_id,
                "mode": "create",
                "title": "4冊目",
                "bookshelf_subject": "数学"
            }
        )
        self.assertEqual(blocked_again.status_code, 403)
        with main.SessionLocal() as db:
            self.assertEqual(db.query(main.StudyTextbook).filter(main.StudyTextbook.user_id == user_id).count(), 3)

    def test_free_roadmap_limit_blocks_fourth_and_delete_reopens_slot(self):
        self.signup()
        created = self.client.post("/api/chat_threads", json={"title": "Java"})
        thread_id = created.json()["thread"]["id"]

        with main.SessionLocal() as db:
            user = db.query(main.User).first()
            user_id = user.id
            for index, subject in enumerate(["英語", "数学", "Python"]):
                db.add(main.StudyRoadmapItem(
                    user_id=user_id,
                    subject=subject,
                    roadmap_title=f"{subject}ロードマップ",
                    goal=f"{subject}を学ぶ",
                    title="基礎",
                    sort_order=index
                ))
            db.commit()

        blocked = self.client.post(
            f"/api/chat/{thread_id}/messages",
            json={"message": "Javaのロードマップを作って"}
        )
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()["error"], "roadmap_limit_reached")
        self.assertEqual(blocked.json()["message"], "無料プランではロードマップは3つまでです。")

        deleted = self.client.request(
            "DELETE",
            "/api/roadmaps",
            json={"subject": "英語", "thread_id": None}
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["plan_usage"]["roadmaps"]["used"], 2)

        original_generator = main.generate_roadmap_plan_with_ai
        main.generate_roadmap_plan_with_ai = lambda *args, **kwargs: {
            "roadmap_title": "Javaロードマップ",
            "goal": "Javaを学ぶ",
            "items": [{"title": "基本文法", "status": "not_started", "reason": "最初の一歩"}]
        }
        try:
            with main.SessionLocal() as db:
                items = main.load_or_create_roadmap(
                    db,
                    user_id,
                    "Java",
                    [],
                    [],
                    thread_id=thread_id,
                    allow_create=True,
                    goal_text="Javaを学ぶ"
                )
        finally:
            main.generate_roadmap_plan_with_ai = original_generator

        self.assertTrue(items)
        self.assertEqual(main.load_plan_usage(user_id)["roadmaps"]["used"], 3)

    def test_premium_plan_has_unlimited_textbooks_and_roadmaps(self):
        self.signup()
        created = self.client.post("/api/chat_threads", json={"title": "Java"})
        thread_id = created.json()["thread"]["id"]

        with main.SessionLocal() as db:
            user = db.query(main.User).first()
            user.subscription_plan = main.PREMIUM_PLAN
            user_id = user.id
            for index in range(3):
                db.add(main.StudyTextbook(
                    user_id=user_id,
                    thread_id=thread_id,
                    subject=f"科目{index}",
                    title=f"教科書{index}"
                ))
            for subject in ["英語", "数学", "Python"]:
                db.add(main.StudyRoadmapItem(
                    user_id=user_id,
                    subject=subject,
                    roadmap_title=f"{subject}ロードマップ",
                    title="基礎"
                ))
            db.commit()

        saved = self.client.post(
            "/api/textbooks/confirm",
            json={
                "thread_id": thread_id,
                "mode": "create",
                "title": "4冊目",
                "bookshelf_subject": "Java"
            }
        )
        self.assertEqual(saved.status_code, 200)

        original_generator = main.generate_roadmap_plan_with_ai
        main.generate_roadmap_plan_with_ai = lambda *args, **kwargs: {
            "roadmap_title": "Javaロードマップ",
            "goal": "Javaを学ぶ",
            "items": [{"title": "基本文法", "status": "not_started", "reason": "最初の一歩"}]
        }
        try:
            with main.SessionLocal() as db:
                items = main.load_or_create_roadmap(
                    db,
                    user_id,
                    "Java",
                    [],
                    [],
                    thread_id=thread_id,
                    allow_create=True,
                    goal_text="Javaを学ぶ"
                )
        finally:
            main.generate_roadmap_plan_with_ai = original_generator

        self.assertTrue(items)
        usage = main.load_plan_usage(user_id)
        self.assertTrue(usage["is_premium"])
        self.assertTrue(usage["textbooks"]["unlimited"])
        self.assertTrue(usage["roadmaps"]["unlimited"])
        self.assertEqual(usage["textbooks"]["used"], 4)
        self.assertEqual(usage["roadmaps"]["used"], 4)

    def test_billing_status_is_safe_when_stripe_is_not_configured(self):
        self.signup()

        response = self.client.get("/api/billing/status")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["billing_configured"])
        self.assertFalse(response.json()["plan_usage"]["is_premium"])
        self.assertFalse(response.json()["can_manage_billing"])

    def test_checkout_is_blocked_until_legal_disclosure_is_configured(self):
        self.signup()
        os.environ["STRIPE_SECRET_KEY"] = "sk_test_unit"
        os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_unit"
        os.environ["STRIPE_PREMIUM_PRICE_ID"] = "price_monthly_800"

        status = self.client.get("/api/billing/status").json()
        self.assertTrue(status["stripe_configured"])
        self.assertFalse(status["legal_disclosure_configured"])
        self.assertFalse(status["billing_configured"])

        response = self.client.post("/api/billing/checkout", json={})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "legal_disclosure_not_configured")

    def test_checkout_uses_verified_monthly_800_yen_price(self):
        self.signup()
        self.configure_stripe()
        stripe_client = self.fake_stripe_client()

        with patch.object(main, "get_stripe_client", return_value=stripe_client):
            response = self.client.post("/api/billing/checkout", json={})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["url"], "https://checkout.stripe.com/c/pay/test")
        stripe_client.v1.prices.retrieve.assert_called_once_with("price_monthly_800")
        checkout_params = stripe_client.v1.checkout.sessions.create.call_args.args[0]
        self.assertEqual(checkout_params["mode"], "subscription")
        self.assertEqual(
            checkout_params["line_items"],
            [{"price": "price_monthly_800", "quantity": 1}]
        )
        self.assertEqual(checkout_params["customer_email"], "test@example.com")
        self.assertIn("session_id={CHECKOUT_SESSION_ID}", checkout_params["success_url"])
        with main.SessionLocal() as db:
            user_id = db.query(main.User).first().id
        self.assertEqual(main.load_plan_usage(user_id)["plan"], main.FREE_PLAN)

    def test_checkout_rejects_a_price_that_is_not_monthly_800_yen(self):
        self.signup()
        self.configure_stripe()
        stripe_client = self.fake_stripe_client(price={
            "id": "price_monthly_800",
            "active": True,
            "currency": "jpy",
            "unit_amount": 900,
            "recurring": {"interval": "month", "interval_count": 1}
        })

        with patch.object(main, "get_stripe_client", return_value=stripe_client):
            response = self.client.post("/api/billing/checkout", json={})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "billing_price_mismatch")
        stripe_client.v1.checkout.sessions.create.assert_not_called()

    def test_signed_webhooks_sync_subscription_and_ignore_old_replays(self):
        self.signup()
        self.configure_stripe()
        with main.SessionLocal() as db:
            user_id = db.query(main.User).first().id

        stripe_client = self.fake_stripe_client()
        events = [
            {
                "type": "customer.subscription.created",
                "created": 100,
                "data": {"object": {
                    "id": "sub_unit",
                    "customer": "cus_unit",
                    "status": "active",
                    "metadata": {"user_id": str(user_id)}
                }}
            },
            {
                "type": "customer.subscription.deleted",
                "created": 200,
                "data": {"object": {
                    "id": "sub_unit",
                    "customer": "cus_unit",
                    "status": "canceled",
                    "metadata": {"user_id": str(user_id)}
                }}
            },
            {
                "type": "customer.subscription.updated",
                "created": 150,
                "data": {"object": {
                    "id": "sub_unit",
                    "customer": "cus_unit",
                    "status": "active",
                    "metadata": {"user_id": str(user_id)}
                }}
            }
        ]
        stripe_client.construct_event.side_effect = events

        with patch.object(main, "get_stripe_client", return_value=stripe_client):
            for _ in events:
                response = self.client.post(
                    "/api/billing/webhook",
                    content=b"{}",
                    headers={
                        "stripe-signature": "signed-test-event",
                        "origin": "https://stripe.com"
                    }
                )
                self.assertEqual(response.status_code, 200)

        with main.SessionLocal() as db:
            user = db.query(main.User).filter(main.User.id == user_id).first()
            self.assertEqual(user.subscription_plan, main.FREE_PLAN)
            self.assertEqual(user.subscription_status, "canceled")
            self.assertEqual(user.stripe_customer_id, "cus_unit")
            self.assertEqual(user.stripe_subscription_id, "sub_unit")

    def test_checkout_reconciliation_and_customer_portal(self):
        self.signup()
        self.configure_stripe()
        with main.SessionLocal() as db:
            user_id = db.query(main.User).first().id

        checkout_session = {
            "id": "cs_test_reconcile",
            "url": "https://checkout.stripe.com/c/pay/test",
            "client_reference_id": str(user_id),
            "status": "complete",
            "payment_status": "paid",
            "customer": "cus_reconcile",
            "subscription": "sub_reconcile",
            "metadata": {"user_id": str(user_id)}
        }
        subscription = {
            "id": "sub_reconcile",
            "customer": "cus_reconcile",
            "status": "active",
            "metadata": {"user_id": str(user_id)}
        }
        stripe_client = self.fake_stripe_client(
            checkout_session=checkout_session,
            subscription=subscription
        )

        with patch.object(main, "get_stripe_client", return_value=stripe_client):
            status_response = self.client.get(
                "/api/billing/status?checkout_session_id=cs_test_reconcile"
            )
            portal_response = self.client.post("/api/billing/portal", json={})

        self.assertEqual(status_response.status_code, 200)
        self.assertTrue(status_response.json()["plan_usage"]["is_premium"])
        self.assertTrue(status_response.json()["can_manage_billing"])
        self.assertEqual(portal_response.status_code, 200)
        self.assertEqual(
            portal_response.json()["url"],
            "https://billing.stripe.com/p/session/test"
        )
        stripe_client.v1.subscriptions.retrieve.assert_called_once_with("sub_reconcile")
        portal_params = stripe_client.v1.billing_portal.sessions.create.call_args.args[0]
        self.assertEqual(portal_params["customer"], "cus_reconcile")

    def test_account_delete_cancels_active_subscription_first(self):
        self.signup()
        self.configure_stripe()
        with main.SessionLocal() as db:
            user = db.query(main.User).first()
            user.subscription_plan = main.PREMIUM_PLAN
            user.subscription_status = "active"
            user.stripe_customer_id = "cus_delete"
            user.stripe_subscription_id = "sub_delete"
            user_id = user.id
            db.commit()

        canceled_subscription = {
            "id": "sub_delete",
            "customer": "cus_delete",
            "status": "canceled",
            "metadata": {"user_id": str(user_id)}
        }
        stripe_client = self.fake_stripe_client(subscription=canceled_subscription)

        with patch.object(main, "get_stripe_client", return_value=stripe_client):
            response = self.client.post(
                "/account/delete",
                data={"password": "password123"},
                follow_redirects=False
            )

        self.assertEqual(response.status_code, 303)
        stripe_client.v1.subscriptions.cancel.assert_called_once_with("sub_delete")
        with main.SessionLocal() as db:
            self.assertIsNone(db.query(main.User).filter(main.User.id == user_id).first())


if __name__ == "__main__":
    unittest.main()
