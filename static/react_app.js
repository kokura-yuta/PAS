(function () {
    if (!window.React || !window.ReactDOM) {
        document.getElementById("pas-react-root").innerHTML =
            '<main class="study-app"><p class="eyebrow">Study PAS</p><h1>読み込みに失敗しました</h1><p class="lead">通信環境を確認して、もう一度開いてください。</p></main>';
        return;
    }

    const h = React.createElement;
    const { useEffect, useRef, useState } = React;

    async function api(path, options) {
        const body = options && options.body;
        const isFormData = body instanceof FormData;
        const response = await fetch(path, {
            credentials: "same-origin",
            headers: isFormData ? undefined : { "Content-Type": "application/json" },
            ...(options || {})
        });

        if (response.status === 401) {
            window.location.href = "/login";
            return null;
        }

        if (!response.ok) {
            throw new Error("request_failed");
        }

        return response.json();
    }

    function App() {
        const [route, setRoute] = useState(window.location.pathname);

        useEffect(function () {
            function handlePopState() {
                setRoute(window.location.pathname);
            }

            window.addEventListener("popstate", handlePopState);
            return function () {
                window.removeEventListener("popstate", handlePopState);
            };
        }, []);

        function navigate(path) {
            window.history.pushState({}, "", path);
            setRoute(path);
            window.scrollTo(0, 0);
        }

        if (route.startsWith("/chat")) {
            return h(ChatScreen, { route, navigate });
        }

        return h(HomeScreen, { navigate });
    }

    function HomeScreen({ navigate }) {
        const [homeData, setHomeData] = useState(null);
        const [subject, setSubject] = useState("");
        const [creating, setCreating] = useState(false);
        const [error, setError] = useState("");

        useEffect(function () {
            let active = true;

            api("/api/home")
                .then(function (data) {
                    if (active) {
                        setHomeData(data);
                    }
                })
                .catch(function () {
                    if (active) {
                        setError("ホームを読み込めませんでした。");
                    }
                });

            return function () {
                active = false;
            };
        }, []);

        async function createSubject(event, directSubject) {
            if (event) {
                event.preventDefault();
            }

            const cleanSubject = (directSubject || subject).trim();

            if (!cleanSubject || creating) {
                return;
            }

            setCreating(true);
            setError("");

            try {
                const data = await api("/api/chat_threads", {
                    method: "POST",
                    body: JSON.stringify({
                        title: cleanSubject,
                        thread_type: "study"
                    })
                });

                if (data && data.url) {
                    navigate(data.url);
                }
            } catch (err) {
                setError("科目チャットを作れませんでした。");
                setCreating(false);
            }
        }

        const examples = homeData ? homeData.subject_examples : [];
        const threads = homeData ? homeData.study_threads : [];
        const userName = homeData && homeData.user ? homeData.user.name : window.PAS_BOOTSTRAP.userName;

        return h(
            "main",
            { className: "study-app study-home" },
            h(
                "header",
                { className: "study-topbar" },
                h(
                    "div",
                    { className: "study-brand" },
                    h("p", { className: "eyebrow" }, "Study PAS"),
                    h("strong", null, "優しい先生")
                ),
                h(
                    "details",
                    { className: "study-menu" },
                    h(
                        "summary",
                        { "aria-label": "メニューを開く" },
                        h("span", null),
                        h("span", null)
                    ),
                    h(
                        "div",
                        { className: "study-menu-panel" },
                        h("p", null, userName),
                        h("a", { href: "/memories" }, "Memory"),
                        h(
                            "form",
                            { method: "post", action: "/logout" },
                            h("button", { type: "submit" }, "ログアウト")
                        )
                    )
                )
            ),
            h(
                "section",
                { className: "study-hero" },
                h("h1", null, "勉強したいことを追加"),
                h(
                    "p",
                    { className: "study-lead" },
                    "科目ごとに先生が変わります。教え方の好みや苦手は、すべての科目で共有されます。"
                ),
                h(
                    "form",
                    { className: "subject-form", onSubmit: createSubject },
                    h("input", {
                        type: "text",
                        value: subject,
                        placeholder: "例: Python、英語、基本情報",
                        onChange: function (event) {
                            setSubject(event.target.value);
                        },
                        disabled: creating
                    }),
                    h("button", { type: "submit", disabled: creating }, creating ? "作成中" : "追加")
                ),
                examples && examples.length
                    ? h(
                        "div",
                        { className: "subject-chips" },
                        examples.map(function (example) {
                            return h(
                                "button",
                                {
                                    key: example,
                                    type: "button",
                                    onClick: function () {
                                        createSubject(null, example);
                                    },
                                    disabled: creating
                                },
                                example
                            );
                        })
                    )
                    : null,
                error ? h("p", { className: "notice" }, error) : null
            ),
            h(
                "section",
                { className: "study-thread-section" },
                h("div", { className: "section-kicker" }, "最近の授業"),
                !homeData
                    ? h("p", { className: "react-loading" }, "読み込み中")
                    : threads && threads.length
                        ? h(
                            "div",
                            { className: "study-thread-list" },
                            threads.map(function (thread) {
                                const context = thread.study_context || {};
                                return h(
                                    "button",
                                    {
                                        key: thread.id,
                                        type: "button",
                                        className: "study-thread-card",
                                        onClick: function () {
                                            navigate(`/chat/${thread.id}`);
                                        }
                                    },
                                    h(
                                        "span",
                                        null,
                                        h("strong", null, thread.display_title),
                                        h("small", null, context.last_studied_label || thread.latest_message)
                                    ),
                                    h("em", null, context.streak_count ? `${context.streak_count}日` : "開始")
                                );
                            })
                        )
                        : h(
                            "div",
                            { className: "study-empty" },
                            h("p", null, "まだ授業はありません。まずは勉強したい科目を追加してください。")
                        )
            )
        );
    }

    function ChatScreen({ route, navigate }) {
        const [chatData, setChatData] = useState(null);
        const [message, setMessage] = useState("");
        const [file, setFile] = useState(null);
        const [sending, setSending] = useState(false);
        const [error, setError] = useState("");
        const fileInputRef = useRef(null);

        const threadIdMatch = route.match(/^\/chat\/(\d+)/);
        const threadId = threadIdMatch ? threadIdMatch[1] : null;
        const apiPath = threadId ? `/api/chat/${threadId}` : "/api/chat";

        useEffect(function () {
            let active = true;
            setChatData(null);
            setError("");
            setFile(null);

            api(apiPath)
                .then(function (data) {
                    if (active) {
                        setChatData(data);
                    }
                })
                .catch(function () {
                    if (active) {
                        setError("授業を読み込めませんでした。");
                    }
                });

            return function () {
                active = false;
            };
        }, [apiPath]);

        useEffect(function () {
            window.scrollTo(0, document.body.scrollHeight);
        }, [chatData, sending]);

        async function sendMessage(event) {
            event.preventDefault();

            const cleanMessage = message.trim();

            if ((!cleanMessage && !file) || !chatData || sending) {
                return;
            }

            setSending(true);
            setError("");

            const optimisticContent = file ? `[画像] ${cleanMessage || "この画像を解説して"}` : cleanMessage;
            setChatData({
                ...chatData,
                messages: chatData.messages.concat([
                    { role: "user", content: optimisticContent, created_at: "" }
                ])
            });
            setMessage("");

            try {
                let data;

                if (file) {
                    const formData = new FormData();
                    formData.append("message", cleanMessage);
                    formData.append("image", file);
                    data = await api(`/api/chat/${chatData.thread.id}/image`, {
                        method: "POST",
                        body: formData
                    });
                } else {
                    data = await api(`/api/chat/${chatData.thread.id}/messages`, {
                        method: "POST",
                        body: JSON.stringify({ message: cleanMessage })
                    });
                }

                if (data) {
                    setChatData(data);
                }

                setFile(null);
                if (fileInputRef.current) {
                    fileInputRef.current.value = "";
                }
            } catch (err) {
                setError("送信できませんでした。もう一度試してください。");
            } finally {
                setSending(false);
            }
        }

        async function deleteThread() {
            if (!chatData || !chatData.thread.can_delete) {
                return;
            }

            if (!window.confirm(`${chatData.thread.title}を削除しますか？`)) {
                return;
            }

            await api(`/api/chat_threads/${chatData.thread.id}`, { method: "DELETE" });
            navigate("/");
        }

        const thread = chatData ? chatData.thread : null;
        const messages = chatData ? chatData.messages : [];
        const context = thread && thread.study_context ? thread.study_context : {};

        return h(
            "main",
            { className: "study-app study-chat" },
            h(
                "header",
                { className: "study-chat-header" },
                h(
                    "button",
                    {
                        type: "button",
                        className: "plain-back",
                        onClick: function () {
                            navigate("/");
                        }
                    },
                    "戻る"
                ),
                h(
                    "div",
                    null,
                    h("p", { className: "eyebrow" }, "優しい先生"),
                    h("h1", null, thread ? thread.title : "Study PAS")
                ),
                thread && thread.can_delete
                    ? h("button", { type: "button", className: "plain-delete", onClick: deleteThread }, "削除")
                    : h("span", null)
            ),
            thread
                ? h(
                    "section",
                    { className: "study-context" },
                    h("p", null, context.status_line || "この科目の授業を始めましょう。"),
                    h(
                        "div",
                        { className: "study-context-grid" },
                        h("span", null, context.last_studied_label || "未学習"),
                        h("span", null, `学習 ${context.session_count || 0}回`),
                        h("span", null, `連続 ${context.streak_count || 0}日`),
                        context.test_date ? h("span", null, `テスト ${context.test_date}`) : null,
                        context.deadline ? h("span", null, `提出 ${context.deadline}`) : null
                    )
                )
                : null,
            error ? h("p", { className: "notice" }, error) : null,
            h(
                "section",
                { className: "study-chat-log" },
                !chatData
                    ? h("div", { className: "study-message teacher-message" }, h("p", null, "読み込み中"))
                    : messages.length
                        ? messages.map(function (chat, index) {
                            return h(
                                "div",
                                {
                                    key: index,
                                    className: `study-message ${chat.role === "user" ? "student-message" : "teacher-message"}`
                                },
                                h("p", null, chat.content)
                            );
                        })
                        : h(
                            "div",
                            { className: "study-message teacher-message" },
                            h("p", null, "分からないところをそのまま送ってください。写真でも大丈夫です。")
                        ),
                sending
                    ? h("div", { className: "study-message teacher-message" }, h("p", null, "考え中..."))
                    : null
            ),
            h(
                "form",
                { className: "study-chat-form", onSubmit: sendMessage },
                h("label", { className: file ? "image-picker has-file" : "image-picker" },
                    "写真",
                    h("input", {
                        ref: fileInputRef,
                        type: "file",
                        accept: "image/*",
                        onChange: function (event) {
                            setFile(event.target.files && event.target.files[0] ? event.target.files[0] : null);
                        },
                        disabled: sending || !chatData
                    })
                ),
                h("input", {
                    type: "text",
                    name: "message",
                    placeholder: file ? "画像について聞きたいこと" : "分からないところを聞く",
                    autoComplete: "off",
                    value: message,
                    onChange: function (event) {
                        setMessage(event.target.value);
                    },
                    disabled: sending || !chatData
                }),
                h("button", { type: "submit", disabled: sending || !chatData || (!message.trim() && !file) }, sending ? "送信中" : "送信")
            )
        );
    }

    ReactDOM.createRoot(document.getElementById("pas-react-root")).render(h(App));
})();
