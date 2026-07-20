import os
import tempfile
import unittest


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
        with main.SessionLocal() as db:
            for table in reversed(main.Base.metadata.sorted_tables):
                db.execute(table.delete())
            db.commit()
        self.client.cookies.clear()

    def signup(self, name="テスト", email="test@example.com", password="password123"):
        return self.client.post(
            "/signup",
            data={"name": name, "email": email, "password": password},
            follow_redirects=False
        )

    def test_health_and_security_headers(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.assertTrue(response.headers["x-request-id"])

    def test_signup_login_logout_flow(self):
        response = self.signup()
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.client.get("/api/home").status_code, 200)

        response = self.client.post("/logout", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.client.get("/api/home").status_code, 401)

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


if __name__ == "__main__":
    unittest.main()
