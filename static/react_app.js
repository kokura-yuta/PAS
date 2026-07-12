(function () {
    if (!window.React || !window.ReactDOM) {
        document.getElementById("pas-react-root").innerHTML =
            '<main class="home home-minimal"><p class="eyebrow">PAS</p><h1>読み込みに失敗しました</h1><p class="lead">通信環境を確認して、もう一度開いてください。</p></main>';
        return;
    }

    const h = React.createElement;
    const { useEffect, useRef, useState } = React;

    async function api(path, options) {
        const response = await fetch(path, {
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json"
            },
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
        const [error, setError] = useState("");
        const [creatingThread, setCreatingThread] = useState(false);

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

        async function createThread() {
            setCreatingThread(true);

            try {
                const data = await api("/api/chat_threads", {
                    method: "POST",
                    body: JSON.stringify({
                        title: "新しい会話",
                        thread_type: "custom"
                    })
                });

                if (data && data.url) {
                    navigate(data.url);
                }
            } catch (err) {
                setError("新しい会話を作れませんでした。");
                setCreatingThread(false);
            }
        }

        const snapshot = homeData ? homeData.home_snapshot : null;
        const todayEvents = snapshot ? snapshot.today_events : [];

        return h(
            "main",
            { className: "home home-minimal react-home" },
            h(
                "header",
                { className: "home-topbar" },
                h(
                    "div",
                    { className: "home-brand" },
                    h("p", { className: "eyebrow" }, "Personal AI System"),
                    h("h1", null, "PAS")
                ),
                h(
                    "details",
                    { className: "home-menu" },
                    h(
                        "summary",
                        { "aria-label": "メニューを開く" },
                        h("span", null),
                        h("span", null)
                    ),
                    h(
                        "div",
                        { className: "home-menu-panel" },
                        h(
                            "div",
                            { className: "home-menu-header" },
                            h("span", null, "Menu"),
                            h("strong", null, homeData ? homeData.user.name : window.PAS_BOOTSTRAP.userName)
                        ),
                        h(
                            "nav",
                            { className: "menu-links" },
                            h("a", { href: "/calendar" }, "予定"),
                            h("a", { href: "/timeline" }, "Timeline"),
                            h("a", { href: "/memories" }, "Memory"),
                            h("a", { href: "/profile" }, "プロフィール"),
                            h("a", { href: "/goals" }, "目標"),
                            h("a", { href: "/settings" }, "設定")
                        ),
                        h(
                            "div",
                            { className: "menu-section" },
                            h("p", null, "会話"),
                            h(
                                "div",
                                { className: "menu-conversation-actions" },
                                h(
                                    "button",
                                    {
                                        type: "button",
                                        onClick: function () {
                                            navigate("/chat");
                                        }
                                    },
                                    "日記"
                                ),
                                h(
                                    "button",
                                    {
                                        type: "button",
                                        onClick: createThread,
                                        disabled: creatingThread
                                    },
                                    creatingThread ? "作成中" : "新しい会話"
                                )
                            )
                        ),
                        h(
                            "form",
                            { className: "menu-logout", method: "post", action: "/logout" },
                            h("button", { type: "submit" }, "ログアウト")
                        )
                    )
                )
            ),
            error ? h("p", { className: "notice" }, error) : null,
            !homeData
                ? h("section", { className: "schedule-panel" }, h("p", { className: "react-loading" }, "読み込み中"))
                : h(
                    "section",
                    { className: "schedule-panel" },
                    h(
                        "div",
                        { className: "schedule-header" },
                        h(
                            "div",
                            null,
                            h("span", null, "Today"),
                            h("h2", null, "今日の予定")
                        ),
                        h("a", { href: "/calendar" }, "追加")
                    ),
                    todayEvents && todayEvents.length
                        ? h(
                            "div",
                            { className: "schedule-list" },
                            todayEvents.map(function (event, index) {
                                return h(
                                    "article",
                                    { key: index },
                                    h("time", null, event.time),
                                    h(
                                        "div",
                                        null,
                                        h("strong", null, event.title),
                                        event.location ? h("p", null, event.location) : null
                                    )
                                );
                            })
                        )
                        : h("div", { className: "schedule-empty" }, h("p", null, "今日の予定はまだありません。"))
                )
        );
    }

    function ChatScreen({ route, navigate }) {
        const [chatData, setChatData] = useState(null);
        const [message, setMessage] = useState("");
        const [sending, setSending] = useState(false);
        const [error, setError] = useState("");
        const logRef = useRef(null);

        const threadIdMatch = route.match(/^\/chat\/(\d+)/);
        const threadId = threadIdMatch ? threadIdMatch[1] : null;
        const apiPath = threadId ? `/api/chat/${threadId}` : "/api/chat";

        useEffect(function () {
            let active = true;
            setChatData(null);
            setError("");

            api(apiPath)
                .then(function (data) {
                    if (active) {
                        setChatData(data);
                    }
                })
                .catch(function () {
                    if (active) {
                        setError("チャットを読み込めませんでした。");
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

            if (!cleanMessage || !chatData || sending) {
                return;
            }

            setSending(true);
            setError("");

            const optimisticMessages = chatData.messages.concat([
                {
                    role: "user",
                    content: cleanMessage,
                    created_at: ""
                }
            ]);

            setChatData({
                ...chatData,
                messages: optimisticMessages
            });
            setMessage("");

            try {
                const data = await api(`/api/chat/${chatData.thread.id}/messages`, {
                    method: "POST",
                    body: JSON.stringify({ message: cleanMessage })
                });

                if (data) {
                    setChatData(data);
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

        return h(
            "main",
            { className: "chat-page react-chat" },
            h(
                "header",
                { className: "chat-header" },
                h(
                    "div",
                    null,
                    h("p", { className: "eyebrow" }, thread ? thread.thread_type_label : "PAS Chat"),
                    h("h1", null, thread ? thread.title : "PAS")
                ),
                h(
                    "div",
                    { className: "chat-actions" },
                    h(
                        "button",
                        {
                            type: "button",
                            onClick: function () {
                                navigate("/");
                            }
                        },
                        "戻る"
                    ),
                    h("a", { href: "/settings" }, "設定")
                )
            ),
            thread && thread.description
                ? h("p", { className: "thread-description" }, thread.description)
                : null,
            chatData
                ? h(
                    "p",
                    { className: "current-persona" },
                    "現在の性格: ",
                    h("strong", null, chatData.settings.default_persona)
                )
                : null,
            thread && thread.can_delete
                ? h(
                    "div",
                    { className: "chat-delete-form" },
                    h("button", { type: "button", onClick: deleteThread }, "チャットを削除")
                )
                : null,
            error ? h("p", { className: "notice" }, error) : null,
            h(
                "section",
                { className: "chat-log", ref: logRef },
                !chatData
                    ? h("div", { className: "message ai-message" }, h("p", null, "読み込み中"))
                    : messages.length
                        ? messages.map(function (chat, index) {
                            return h(
                                "div",
                                {
                                    key: index,
                                    className: `message ${chat.role === "user" ? "user-message" : "ai-message"}`
                                },
                                h("p", null, chat.content)
                            );
                        })
                        : h(
                            "div",
                            { className: "message ai-message" },
                            h("p", null, "まだ会話はありません。最初のメッセージを送ってみてください。")
                        ),
                sending
                    ? h("div", { className: "message ai-message" }, h("p", null, "考え中..."))
                    : null
            ),
            h(
                "form",
                { className: "chat-form", onSubmit: sendMessage },
                h("input", {
                    type: "text",
                    name: "message",
                    placeholder: "メッセージを入力...",
                    autoComplete: "off",
                    value: message,
                    onChange: function (event) {
                        setMessage(event.target.value);
                    },
                    disabled: sending || !chatData,
                    required: true
                }),
                h("button", { type: "submit", disabled: sending || !chatData }, sending ? "送信中" : "送信")
            )
        );
    }

    ReactDOM.createRoot(document.getElementById("pas-react-root")).render(h(App));
})();
