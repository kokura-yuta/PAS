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
        const [screenState, setScreenState] = useState("entered");
        const [transitionDirection, setTransitionDirection] = useState("forward");
        const [transitionMessage, setTransitionMessage] = useState("");
        const routeRef = useRef(window.location.pathname);
        const transitionTimerRef = useRef(null);
        const lastHapticAtRef = useRef(0);

        useEffect(function () {
            function handlePopState() {
                const nextPath = window.location.pathname;
                changeRoute(nextPath, {
                    direction: nextPath.startsWith("/chat") ? "forward" : "back",
                    updateHistory: false,
                    message: nextPath.startsWith("/chat") ? "授業を準備しています" : "ホームへ戻っています"
                });
            }

            function handlePointerDown(event) {
                const target = event.target.closest(
                    "button, summary, a, .image-picker, .study-history-row, .study-thread-card"
                );
                const root = document.getElementById("pas-react-root");
                const now = Date.now();

                if (!target || !root || !root.contains(target)) {
                    return;
                }

                if (target.disabled || target.getAttribute("aria-disabled") === "true") {
                    return;
                }

                if (now - lastHapticAtRef.current < 120) {
                    return;
                }

                lastHapticAtRef.current = now;
                triggerSoftHaptic();
            }

            window.addEventListener("popstate", handlePopState);
            document.addEventListener("pointerdown", handlePointerDown, { passive: true });
            return function () {
                window.removeEventListener("popstate", handlePopState);
                document.removeEventListener("pointerdown", handlePointerDown);
                if (transitionTimerRef.current) {
                    window.clearTimeout(transitionTimerRef.current);
                }
            };
        }, []);

        function changeRoute(path, options) {
            const settings = options || {};

            if (!path || path === routeRef.current) {
                return;
            }

            if (transitionTimerRef.current) {
                window.clearTimeout(transitionTimerRef.current);
            }

            setTransitionDirection(settings.direction || "forward");
            setTransitionMessage(settings.message || "授業を準備しています");
            setScreenState("exiting");

            transitionTimerRef.current = window.setTimeout(function () {
                if (settings.updateHistory !== false) {
                    window.history.pushState({}, "", path);
                }

                routeRef.current = path;
                setRoute(path);
                window.scrollTo({ top: 0, behavior: "auto" });
                setScreenState("entering");

                window.requestAnimationFrame(function () {
                    setScreenState("entered");
                });

                window.setTimeout(function () {
                    setTransitionMessage("");
                }, 260);
            }, 170);
        }

        function navigate(path, options) {
            changeRoute(path, {
                direction: options && options.direction ? options.direction : "forward",
                message: options && options.message ? options.message : "授業を準備しています"
            });
        }

        let screen;

        if (route.startsWith("/chat")) {
            screen = h(ChatScreen, { route, navigate });
        } else if (route === "/bookshelves") {
            screen = h(BookshelvesScreen, { navigate });
        } else if (route.startsWith("/bookshelf/")) {
            screen = h(BookshelfScreen, { route, navigate });
        } else if (route.startsWith("/textbook/")) {
            screen = h(TextbookScreen, { route, navigate });
        } else {
            screen = h(HomeScreen, { navigate });
        }
        const screenClass = [
            "study-screen",
            `study-screen-${screenState}`,
            `study-screen-${transitionDirection}`
        ].join(" ");

        return h(
            "div",
            { className: "study-route-frame" },
            transitionMessage
                ? h(
                    "div",
                    { className: "route-loading", role: "status", "aria-live": "polite" },
                    h("span", { className: "mini-spinner" }),
                    transitionMessage
                )
                : null,
            h("div", { className: screenClass }, screen)
        );
    }

    function LoadingLabel({ text }) {
        return h(
            "span",
            { className: "loading-label" },
            h("span", { className: "mini-spinner" }),
            text
        );
    }

    function triggerSoftHaptic() {
        if (!window.navigator || typeof window.navigator.vibrate !== "function") {
            return;
        }

        window.navigator.vibrate(8);
    }

    function ThinkingBubble({ label }) {
        return h(
            "div",
            { className: "study-message teacher-message thinking-message", role: "status", "aria-live": "polite" },
            h("span", { className: "mini-spinner" }),
            h("p", null, label || "先生が考えています")
        );
    }

    function HomeScreen({ navigate }) {
        const [homeData, setHomeData] = useState(null);
        const [subject, setSubject] = useState("");
        const [creating, setCreating] = useState(false);
        const [openingPath, setOpeningPath] = useState("");
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
                    setOpeningPath(data.url);
                    navigate(data.url, { message: "新しい授業を準備しています" });
                }
            } catch (err) {
                setError("科目チャットを作れませんでした。");
                setCreating(false);
                setOpeningPath("");
            }
        }

        function openStudyPath(path, message) {
            setOpeningPath(path);
            navigate(path, { message: message || "授業を準備しています" });
        }

        const examples = homeData ? homeData.subject_examples : [];
        const threads = homeData ? homeData.study_threads : [];
        const nextThread = homeData ? homeData.next_study_thread : null;
        const recentHistory = homeData ? homeData.recent_study_history : [];
        const memoryHighlights = homeData ? homeData.memory_highlights : [];
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
                        h(
                            "button",
                            {
                                type: "button",
                                onClick: function () {
                                    navigate("/bookshelves", { message: "本棚を開いています" });
                                }
                            },
                            "本棚"
                        ),
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
                h("p", { className: "section-kicker" }, "Today"),
                h("h1", null, "今日は何を勉強しますか？"),
                h(
                    "p",
                    { className: "study-lead" },
                    "科目ごとに先生が変わり、教え方の好みや苦手はすべての授業で共有されます。"
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
                    h(
                        "button",
                        { type: "submit", disabled: creating },
                        creating ? h(LoadingLabel, { text: "作成中" }) : "+ 新しい学習"
                    )
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
            nextThread
                ? h(
                    "section",
                    { className: "continue-card" },
                    h("p", { className: "section-kicker" }, "前回の続き"),
                    h("div", { className: "continue-main" },
                        h("span", null, nextThread.display_title),
                        h("strong", null, nextThread.next_lesson_label)
                    ),
                    h(
                        "button",
                        {
                            type: "button",
                            onClick: function () {
                                openStudyPath(`/chat/${nextThread.id}`, "前回の内容を確認しています");
                            }
                        },
                        openingPath === `/chat/${nextThread.id}`
                            ? h(LoadingLabel, { text: "準備中" })
                            : "続きから始める"
                    )
                )
                : null,
            recentHistory && recentHistory.length
                ? h(
                    "section",
                    { className: "study-history-section" },
                    h("div", { className: "section-kicker" }, "最近勉強した内容"),
                    h(
                        "div",
                        { className: "study-history-list" },
                        recentHistory.map(function (item) {
                            return h(
                                "button",
                                {
                                    key: item.id,
                                    type: "button",
                                    className: "study-history-row",
                                    onClick: function () {
                                        openStudyPath(item.url, "前回の内容を確認しています");
                                    }
                                },
                                h("span", null, item.day_label),
                                h("strong", null, item.title),
                                h(
                                    "small",
                                    null,
                                    openingPath === item.url ? h(LoadingLabel, { text: "準備中" }) : item.summary
                                )
                            );
                        })
                    )
                )
                : null,
            memoryHighlights && memoryHighlights.length
                ? h(
                    "section",
                    { className: "teacher-memory-card" },
                    h("p", { className: "section-kicker" }, "先生が覚えていること"),
                    h(
                        "ul",
                        null,
                        memoryHighlights.map(function (memory) {
                            return h("li", { key: memory.id }, memory.content);
                        })
                    )
                )
                : null,
            h(
                "section",
                { className: "study-thread-section" },
                h("div", { className: "section-kicker" }, "授業"),
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
                                            openStudyPath(`/chat/${thread.id}`, "授業を準備しています");
                                        }
                                    },
                                    h(
                                        "span",
                                        null,
                                        h("strong", null, thread.display_title),
                                        h("small", null, context.last_studied_label || thread.latest_message)
                                    ),
                                    h(
                                        "em",
                                        null,
                                        openingPath === `/chat/${thread.id}`
                                            ? h("span", { className: "mini-spinner" })
                                            : (context.streak_count ? `${context.streak_count}日` : "開始")
                                    )
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

    function BookshelvesScreen({ navigate }) {
        const [data, setData] = useState(null);
        const [error, setError] = useState("");

        useEffect(function () {
            let active = true;

            api("/api/bookshelves")
                .then(function (response) {
                    if (active) {
                        setData(response);
                    }
                })
                .catch(function () {
                    if (active) {
                        setError("本棚を読み込めませんでした。");
                    }
                });

            return function () {
                active = false;
            };
        }, []);

        const bookshelves = data ? data.bookshelves : [];

        return h(
            "main",
            { className: "study-app study-library" },
            h(
                "header",
                { className: "study-chat-header library-header" },
                h(
                    "button",
                    {
                        type: "button",
                        className: "plain-back",
                        onClick: function () {
                            navigate("/", { direction: "back", message: "ホームへ戻っています" });
                        }
                    },
                    "戻る"
                ),
                h(
                    "div",
                    null,
                    h("p", { className: "eyebrow" }, "Bookshelf"),
                    h("h1", null, "本棚")
                ),
                h("span", null)
            ),
            h(
                "section",
                { className: "library-intro" },
                h("p", { className: "section-kicker" }, "自分専用の教科書"),
                h("h2", null, "授業から作った教科書を、分野ごとに読む。"),
                h("p", null, "教科書はユーザーが承認した内容だけ保存されます。")
            ),
            error ? h("p", { className: "notice" }, error) : null,
            !data
                ? h("p", { className: "react-loading" }, "読み込み中")
                : bookshelves.length
                    ? h(
                        "section",
                        { className: "bookshelf-grid" },
                        bookshelves.map(function (shelf) {
                            return h(
                                "button",
                                {
                                    key: shelf.subject,
                                    type: "button",
                                    className: "bookshelf-card",
                                    onClick: function () {
                                        navigate(shelf.url, { message: "本棚を開いています" });
                                    }
                                },
                                h("span", null, shelf.subject),
                                h("strong", null, `${shelf.textbook_count}冊`),
                                h("small", null, shelf.latest_updated_at ? `更新 ${shelf.latest_updated_at}` : "まだ教科書はありません")
                            );
                        })
                    )
                    : h(
                        "section",
                        { className: "study-empty" },
                        h("p", null, "まだ本棚はありません。授業画面から「教科書にする」を押すと作れます。")
                    )
        );
    }

    function BookshelfScreen({ route, navigate }) {
        const subject = decodeURIComponent(route.replace(/^\/bookshelf\//, ""));
        const [data, setData] = useState(null);
        const [error, setError] = useState("");

        useEffect(function () {
            let active = true;
            setData(null);
            setError("");

            api(`/api/bookshelves/${encodeURIComponent(subject)}`)
                .then(function (response) {
                    if (active) {
                        setData(response);
                    }
                })
                .catch(function () {
                    if (active) {
                        setError("この本棚を読み込めませんでした。");
                    }
                });

            return function () {
                active = false;
            };
        }, [subject]);

        const textbooks = data ? data.textbooks : [];

        return h(
            "main",
            { className: "study-app study-library" },
            h(
                "header",
                { className: "study-chat-header library-header" },
                h(
                    "button",
                    {
                        type: "button",
                        className: "plain-back",
                        onClick: function () {
                            navigate("/bookshelves", { direction: "back", message: "本棚へ戻っています" });
                        }
                    },
                    "戻る"
                ),
                h(
                    "div",
                    null,
                    h("p", { className: "eyebrow" }, "Bookshelf"),
                    h("h1", null, subject || "本棚")
                ),
                h("span", null)
            ),
            error ? h("p", { className: "notice" }, error) : null,
            !data
                ? h("p", { className: "react-loading" }, "読み込み中")
                : textbooks.length
                    ? h(
                        "section",
                        { className: "textbook-list" },
                        textbooks.map(function (textbook) {
                            return h(
                                "button",
                                {
                                    key: textbook.id,
                                    type: "button",
                                    className: "textbook-card",
                                    onClick: function () {
                                        navigate(textbook.url, { message: "教科書を開いています" });
                                    }
                                },
                                h("span", null, textbook.subject),
                                h("strong", null, textbook.title),
                                h("small", null, `作成 ${textbook.created_at || "-"} / 更新 ${textbook.updated_at || "-"}`)
                            );
                        })
                    )
                    : h(
                        "section",
                        { className: "study-empty" },
                        h("p", null, "この分野の教科書はまだありません。授業画面から作成できます。")
                    )
        );
    }

    function TextbookScreen({ route, navigate }) {
        const textbookIdMatch = route.match(/^\/textbook\/(\d+)/);
        const textbookId = textbookIdMatch ? textbookIdMatch[1] : "";
        const [data, setData] = useState(null);
        const [error, setError] = useState("");

        useEffect(function () {
            let active = true;
            setData(null);
            setError("");

            api(`/api/textbooks/${textbookId}`)
                .then(function (response) {
                    if (active) {
                        setData(response);
                    }
                })
                .catch(function () {
                    if (active) {
                        setError("教科書を読み込めませんでした。");
                    }
                });

            return function () {
                active = false;
            };
        }, [textbookId]);

        const textbook = data ? data.textbook : null;
        const sections = textbook ? textbook.sections.filter(function (section) {
            return section.content && section.content.trim();
        }) : [];

        return h(
            "main",
            { className: "study-app study-textbook-page" },
            h(
                "header",
                { className: "study-chat-header library-header" },
                h(
                    "button",
                    {
                        type: "button",
                        className: "plain-back",
                        onClick: function () {
                            const subject = textbook ? textbook.subject : "";
                            navigate(subject ? `/bookshelf/${encodeURIComponent(subject)}` : "/bookshelves", {
                                direction: "back",
                                message: "本棚へ戻っています"
                            });
                        }
                    },
                    "戻る"
                ),
                h(
                    "div",
                    null,
                    h("p", { className: "eyebrow" }, textbook ? textbook.subject : "Textbook"),
                    h("h1", null, textbook ? textbook.title : "教科書")
                ),
                h("span", null)
            ),
            error ? h("p", { className: "notice" }, error) : null,
            !textbook
                ? h("p", { className: "react-loading" }, "読み込み中")
                : h(
                    React.Fragment,
                    null,
                    h(
                        "section",
                        { className: "textbook-meta-card" },
                        h("span", null, `作成 ${textbook.created_at || "-"}`),
                        h("span", null, `更新 ${textbook.updated_at || "-"}`),
                        h("span", null, textbook.subject)
                    ),
                    h(
                        "article",
                        { className: "textbook-reader" },
                        sections.map(function (section) {
                            return h(
                                "section",
                                { key: section.key, className: "textbook-section" },
                                h("h2", null, section.label),
                                h("p", null, section.content)
                            );
                        })
                    ),
                    textbook.updates && textbook.updates.length
                        ? h(
                            "section",
                            { className: "textbook-updates" },
                            h("h2", null, "更新履歴"),
                            textbook.updates.map(function (update) {
                                return h(
                                    "p",
                                    { key: update.id },
                                    `${update.created_at}: ${update.summary}`
                                );
                            })
                        )
                        : null,
                    h(
                        "button",
                        {
                            type: "button",
                            className: "ask-teacher-button",
                            onClick: function () {
                                navigate(`/chat/${textbook.thread_id}`, { message: "先生の授業へ戻っています" });
                            }
                        },
                        "この内容を先生に質問する"
                    )
                )
        );
    }

    function ChatScreen({ route, navigate }) {
        const [chatData, setChatData] = useState(null);
        const [message, setMessage] = useState("");
        const [file, setFile] = useState(null);
        const [sending, setSending] = useState(false);
        const [sendingLabel, setSendingLabel] = useState("");
        const [error, setError] = useState("");
        const [textbookPreview, setTextbookPreview] = useState(null);
        const [previewingTextbook, setPreviewingTextbook] = useState(false);
        const [savingTextbook, setSavingTextbook] = useState(false);
        const fileInputRef = useRef(null);

        const threadIdMatch = route.match(/^\/chat\/(\d+)/);
        const threadId = threadIdMatch ? threadIdMatch[1] : null;
        const apiPath = threadId ? `/api/chat/${threadId}` : "/api/chat";

        useEffect(function () {
            let active = true;
            setChatData(null);
            setError("");
            setFile(null);
            setTextbookPreview(null);

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
            window.requestAnimationFrame(function () {
                window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
            });
        }, [chatData, sending]);

        async function postTextMessage(cleanMessage, displayMessage) {
            if (!cleanMessage || !chatData || sending) {
                return;
            }

            setSending(true);
            setSendingLabel("先生が考えています");
            setError("");
            setChatData({
                ...chatData,
                messages: chatData.messages.concat([
                    { role: "user", content: displayMessage || cleanMessage, created_at: "" }
                ])
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
                setSendingLabel("");
            }
        }

        async function sendMessage(event) {
            event.preventDefault();

            const cleanMessage = message.trim();

            if (!file) {
                await postTextMessage(cleanMessage);
                return;
            }

            if ((!cleanMessage && !file) || !chatData || sending) {
                return;
            }

            setSending(true);
            setSendingLabel("画像を読み取っています");
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
                setSendingLabel("");
            }
        }

        function sendLessonAction(action) {
            postTextMessage(action.message, action.label);
        }

        async function createTextbookPreview() {
            if (!chatData || previewingTextbook || savingTextbook) {
                return;
            }

            setPreviewingTextbook(true);
            setError("");
            setTextbookPreview(null);

            try {
                const data = await api(`/api/chat/${chatData.thread.id}/textbook_preview`, {
                    method: "POST",
                    body: JSON.stringify({ source_note: "" })
                });

                if (data && data.preview) {
                    setTextbookPreview(data.preview);
                    window.setTimeout(function () {
                        const preview = document.querySelector(".textbook-preview-card");
                        if (preview) {
                            preview.scrollIntoView({ behavior: "smooth", block: "center" });
                        }
                    }, 80);
                }
            } catch (err) {
                setError("教科書プレビューを作れませんでした。もう一度試してください。");
            } finally {
                setPreviewingTextbook(false);
            }
        }

        async function confirmTextbookPreview() {
            if (!chatData || !textbookPreview || savingTextbook) {
                return;
            }

            setSavingTextbook(true);
            setError("");

            try {
                const data = await api("/api/textbooks/confirm", {
                    method: "POST",
                    body: JSON.stringify({
                        thread_id: chatData.thread.id,
                        mode: textbookPreview.mode || "create",
                        target_textbook_id: textbookPreview.target_textbook_id || null,
                        title: textbookPreview.title || "",
                        bookshelf_subject: textbookPreview.bookshelf_subject || chatData.thread.title,
                        basic_explanation: textbookPreview.basic_explanation || "",
                        concrete_examples: textbookPreview.concrete_examples || "",
                        key_points: textbookPreview.key_points || "",
                        weak_points: textbookPreview.weak_points || "",
                        unclear_points: textbookPreview.unclear_points || "",
                        common_mistakes: textbookPreview.common_mistakes || "",
                        check_questions: textbookPreview.check_questions || "",
                        application_questions: textbookPreview.application_questions || "",
                        model_answers: textbookPreview.model_answers || "",
                        detailed_explanations: textbookPreview.detailed_explanations || "",
                        related_textbooks: textbookPreview.related_textbooks || "",
                        update_summary: textbookPreview.update_summary || ""
                    })
                });

                if (data && data.textbook) {
                    setTextbookPreview(null);
                    navigate(data.textbook.url, { message: "教科書を開いています" });
                }
            } catch (err) {
                setError("教科書を保存できませんでした。もう一度試してください。");
            } finally {
                setSavingTextbook(false);
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
            navigate("/", { direction: "back", message: "ホームへ戻っています" });
        }

        const thread = chatData ? chatData.thread : null;
        const messages = chatData ? chatData.messages : [];
        const context = thread && thread.study_context ? thread.study_context : {};
        const lessonActions = [
            {
                label: "理解確認",
                message: "ここまでの内容で、理解確認の問題を1問だけ出してください。"
            },
            {
                label: "応用問題",
                message: "今の内容を使った小さな応用問題を1問だけ出してください。"
            },
            {
                label: "今日のまとめ",
                message: "今日学んだ内容を短くまとめて、次に復習するポイントを教えてください。"
            },
            {
                label: "今日はここまで",
                message: "今日はここまでにします。学習レポートとして、今日できたこと、まだ曖昧なこと、次回やることを短くまとめてください。"
            }
        ];

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
                            navigate("/", { direction: "back", message: "ホームへ戻っています" });
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
                    ? h(ThinkingBubble, { label: sendingLabel })
                    : null
            ),
            textbookPreview
                ? h(
                    "section",
                    { className: "textbook-preview-card" },
                    h(
                        "div",
                        { className: "textbook-preview-head" },
                        h("p", { className: "section-kicker" }, textbookPreview.mode === "update" ? "更新プレビュー" : "作成プレビュー"),
                        h("h2", null, textbookPreview.title || "教科書プレビュー"),
                        h(
                            "small",
                            null,
                            textbookPreview.mode === "update" && textbookPreview.target_textbook_title
                                ? `更新先: ${textbookPreview.target_textbook_title}`
                                : `保存先の本棚: ${textbookPreview.bookshelf_subject || thread.title}`
                        )
                    ),
                    h(
                        "div",
                        { className: "textbook-preview-body" },
                        h("strong", null, "追加予定の内容"),
                        h("p", null, textbookPreview.update_summary || textbookPreview.basic_explanation || "直近の授業内容を教科書に整理します。")
                    ),
                    h(
                        "details",
                        { className: "textbook-preview-details" },
                        h("summary", null, "内容を確認する"),
                        ["basic_explanation", "key_points", "weak_points", "unclear_points", "check_questions", "application_questions"].map(function (field) {
                            const labels = {
                                basic_explanation: "基本説明",
                                key_points: "重要ポイント",
                                weak_points: "苦手ポイント",
                                unclear_points: "まだ曖昧な内容",
                                check_questions: "理解確認問題",
                                application_questions: "応用問題"
                            };
                            return textbookPreview[field]
                                ? h(
                                    "div",
                                    { key: field },
                                    h("h3", null, labels[field]),
                                    h("p", null, textbookPreview[field])
                                )
                                : null;
                        })
                    ),
                    h(
                        "div",
                        { className: "textbook-preview-actions" },
                        h(
                            "button",
                            {
                                type: "button",
                                onClick: confirmTextbookPreview,
                                disabled: savingTextbook
                            },
                            savingTextbook
                                ? h(LoadingLabel, { text: "保存中" })
                                : (textbookPreview.mode === "update" ? "更新する" : "教科書を作成")
                        ),
                        h(
                            "button",
                            {
                                type: "button",
                                className: "secondary-button",
                                onClick: function () {
                                    setTextbookPreview(null);
                                },
                                disabled: savingTextbook
                            },
                            textbookPreview.mode === "update" ? "今回は更新しない" : "今回は作成しない"
                        )
                    )
                )
                : null,
            h(
                "div",
                { className: "study-chat-controls" },
                h(
                    "section",
                    { className: "lesson-actions", "aria-label": "授業アクション" },
                    h(
                        "button",
                        {
                            type: "button",
                            className: "textbook-action",
                            onClick: createTextbookPreview,
                            disabled: previewingTextbook || savingTextbook || !chatData
                        },
                        previewingTextbook ? h(LoadingLabel, { text: "作成中" }) : "教科書にする"
                    ),
                    lessonActions.map(function (action) {
                        return h(
                            "button",
                            {
                                key: action.label,
                                type: "button",
                                onClick: function () {
                                    sendLessonAction(action);
                                },
                                disabled: sending || !chatData
                            },
                            action.label
                        );
                    })
                ),
                h(
                    "form",
                    { className: "study-chat-form", onSubmit: sendMessage },
                    h("label", { className: file ? "image-picker has-file" : "image-picker" },
                        sending && file ? h("span", { className: "mini-spinner" }) : (file ? "選択中" : "写真"),
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
                    h(
                        "button",
                        { type: "submit", disabled: sending || !chatData || (!message.trim() && !file) },
                        sending ? h(LoadingLabel, { text: "送信中" }) : "送信"
                    )
                )
            )
        );
    }

    ReactDOM.createRoot(document.getElementById("pas-react-root")).render(h(App));
})();
