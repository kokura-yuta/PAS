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

    function parseSseBlock(block) {
        const lines = block.split("\n");
        let eventName = "message";
        const dataLines = [];

        lines.forEach(function (line) {
            if (line.startsWith("event:")) {
                eventName = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
                dataLines.push(line.slice(5).trimStart());
            }
        });

        return {
            event: eventName,
            data: dataLines.join("\n")
        };
    }

    async function streamApi(path, options, onEvent) {
        const response = await fetch(path, {
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            ...(options || {})
        });

        if (response.status === 401) {
            window.location.href = "/login";
            return;
        }

        if (!response.ok || !response.body) {
            throw new Error("request_failed");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const result = await reader.read();

            if (result.done) {
                break;
            }

            buffer += decoder.decode(result.value, { stream: true });
            const blocks = buffer.split("\n\n");
            buffer = blocks.pop() || "";

            blocks.forEach(function (block) {
                if (!block.trim()) {
                    return;
                }

                const parsed = parseSseBlock(block);
                let data = {};

                try {
                    data = parsed.data ? JSON.parse(parsed.data) : {};
                } catch (err) {
                    data = {};
                }

                onEvent(parsed.event, data);
            });
        }

        if (buffer.trim()) {
            const parsed = parseSseBlock(buffer);
            let data = {};

            try {
                data = parsed.data ? JSON.parse(parsed.data) : {};
            } catch (err) {
                data = {};
            }

            onEvent(parsed.event, data);
        }
    }

    const THINKING_LABELS = [
        "先生が前回の内容を確認しています",
        "理解度を見ています",
        "ロードマップを確認しています",
        "教科書に残す内容を整理しています"
    ];

    const IMAGE_THINKING_LABELS = [
        "画像を読み取っています",
        "問題の内容を整理しています",
        "理解度と教科書を確認しています",
        "授業の進め方を準備しています"
    ];

    function normalizeTextbookSectionContent(content, compact) {
        const normalized = String(content || "")
            .replace(/\r\n?/g, "\n")
            .split("\n")
            .map(function (line) {
                return line
                    .replace(/^[\s\u00A0\u200B\uFEFF\u3000]+$/g, "")
                    .replace(/[\s\u00A0\u200B\uFEFF\u3000]+$/g, "");
            })
            .join("\n")
            .trim();

        return compact
            ? normalized.replace(/\n{2,}/g, "\n")
            : normalized.replace(/\n{3,}/g, "\n\n");
    }

    const KOREAN_CHARACTER_PATTERN = /[\u1100-\u11FF\u3130-\u318F\uAC00-\uD7AF\uA960-\uA97F\uD7B0-\uD7FF]/;
    const KOREAN_CHARACTER_GLOBAL_PATTERN = /[\u1100-\u11FF\u3130-\u318F\uAC00-\uD7AF\uA960-\uA97F\uD7B0-\uD7FF]/g;

    const LANGUAGE_AUDIO_CONTEXTS = [
        {
            key: "english",
            label: "英語",
            lang: "en-US",
            contextPattern: /英語|英文|英単語|TOEIC|リスニング|シャドーイング|English|Listening/i,
            textPattern: /[A-Za-z][A-Za-z'’-]*/
        },
        {
            key: "korean",
            label: "韓国語",
            lang: "ko-KR",
            contextPattern: /韓国語|ハングル|Korean/i,
            textPattern: KOREAN_CHARACTER_PATTERN
        },
        {
            key: "chinese",
            label: "中国語",
            lang: "zh-CN",
            contextPattern: /中国語|中文|Chinese|HSK/i,
            textPattern: /[\u4E00-\u9FFF]/
        },
        {
            key: "japanese",
            label: "日本語",
            lang: "ja-JP",
            contextPattern: /日本語|Japanese|JLPT|ひらがな|カタカナ|漢字/i,
            textPattern: /[\u3040-\u30ff\u4E00-\u9FFF]/
        }
    ];

    const LANGUAGE_AUDIO_SECTION_PATTERN = /理解確認|応用問題|問題|例題|練習|クイズ|リスニング|シャドーイング|ディクテーション|発音|音読|会話文|長文|選択肢|空欄|穴埋め|和訳|英訳|聞き取り|TOEIC|HSK|JLPT/i;
    const LANGUAGE_AUDIO_TEXTBOOK_SECTION_PATTERN = /リスニング用問題|リスニング問題|発音問題|発音練習/i;
    const LANGUAGE_AUDIO_MANUAL_REQUEST_PATTERN = /(?:音声(?:用)?|再生用|読み上げ用|Audio)\s*[:：]/i;
    const LANGUAGE_AUDIO_TEXT_PATTERN = /問題|例題|練習|クイズ|単語問題|語彙問題|Vocabulary|リスニング|シャドーイング|ディクテーション|発音|音読|会話文|長文|選択肢|空欄|穴埋め|和訳|英訳|聞き取り|TOEIC|HSK|JLPT|次の.*訳|次の.*読|次の.*選/i;
    const LANGUAGE_AUDIO_LINE_MARKER_PATTERN = /^(Q|Question|問|問題|No\.|[0-9０-９]+[.)．、]|[①②③④⑤⑥⑦⑧⑨⑩]|[A-DＡ-Ｄア-エ][.)．、])/i;

    function isSpeechAvailable() {
        return "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
    }

    function getSpeechRecognitionConstructor() {
        return window.SpeechRecognition || window.webkitSpeechRecognition || null;
    }

    function getLanguageContext(contextLabel) {
        const context = contextLabel || "";

        return LANGUAGE_AUDIO_CONTEXTS.find(function (language) {
            return language.contextPattern.test(context);
        }) || null;
    }

    function hasConversationLanguageAudioText(text, contextLabel) {
        const value = String(text || "");

        return LANGUAGE_AUDIO_MANUAL_REQUEST_PATTERN.test(value);
    }

    function detectLanguageFromText(text) {
        const value = String(text || "");
        const detectionValue = LANGUAGE_AUDIO_MANUAL_REQUEST_PATTERN.test(value)
            ? value.replace(/^.*?(音声(?:用)?|再生用|読み上げ用|Audio)\s*[:：]\s*/i, "")
            : value;

        if (KOREAN_CHARACTER_PATTERN.test(detectionValue)) {
            return LANGUAGE_AUDIO_CONTEXTS.find(function (language) {
                return language.key === "korean";
            });
        }

        if (/[A-Za-z][A-Za-z'’-]*/.test(detectionValue)) {
            const words = detectionValue.match(/[A-Za-z][A-Za-z'’-]*/g) || [];
            const englishCharacters = words.join("").length;
            const totalCharacters = detectionValue.replace(/\s/g, "").length || 1;

            if (
                englishCharacters >= 2 &&
                (
                    LANGUAGE_AUDIO_MANUAL_REQUEST_PATTERN.test(value) ||
                    words.length === 1 ||
                    (words.length >= 3 && englishCharacters >= 12 && englishCharacters / totalCharacters > 0.35)
                )
            ) {
                return LANGUAGE_AUDIO_CONTEXTS.find(function (language) {
                    return language.key === "english";
                });
            }
        }

        if (/[\u3040-\u30ff]/.test(detectionValue)) {
            return LANGUAGE_AUDIO_CONTEXTS.find(function (language) {
                return language.key === "japanese";
            });
        }

        if (/[\u4E00-\u9FFF]/.test(detectionValue)) {
            return LANGUAGE_AUDIO_CONTEXTS.find(function (language) {
                return language.key === "chinese";
            });
        }

        return null;
    }

    function detectLanguageTarget(text, contextLabel, sourceType) {
        const contextLanguage = getLanguageContext(contextLabel);
        const textLanguage = detectLanguageFromText(text);
        const allowJapaneseFromText = sourceType === "selection";
        const language = contextLanguage || (
            textLanguage && (textLanguage.key !== "japanese" || allowJapaneseFromText)
                ? textLanguage
                : null
        );

        if (!language) {
            return null;
        }

        if (!isLanguageExerciseAudioContext(text, contextLabel, sourceType)) {
            return null;
        }

        const speechText = extractLanguageAudioText(text, language, contextLabel, sourceType);

        if (!speechText) {
            return null;
        }

        return {
            language: language,
            text: speechText,
            sentences: splitLanguageSentences(speechText, language)
        };
    }

    function isLanguageExerciseAudioContext(text, contextLabel, sourceType) {
        const context = String(contextLabel || "");
        const value = String(text || "");

        if (sourceType === "textbook") {
            return LANGUAGE_AUDIO_TEXTBOOK_SECTION_PATTERN.test(context);
        }

        if (sourceType === "chat") {
            return hasConversationLanguageAudioText(value, context);
        }

        if (sourceType === "selection") {
            return Boolean(value.trim());
        }

        return LANGUAGE_AUDIO_SECTION_PATTERN.test(context) || LANGUAGE_AUDIO_TEXT_PATTERN.test(value);
    }

    function hasLanguageAudioMarker(line) {
        const value = String(line || "").trim();

        return LANGUAGE_AUDIO_TEXT_PATTERN.test(value) || LANGUAGE_AUDIO_LINE_MARKER_PATTERN.test(value);
    }

    function lineMatchesLanguage(line, language) {
        if (language.key === "english") {
            const words = line.match(/[A-Za-z][A-Za-z'’-]*/g) || [];
            const englishCharacters = words.join("").length;
            const totalCharacters = line.replace(/\s/g, "").length || 1;

            return englishCharacters >= 2 && (words.length === 1 || englishCharacters / totalCharacters > 0.35);
        }

        if (language.key === "korean") {
            return (line.match(KOREAN_CHARACTER_GLOBAL_PATTERN) || []).length >= 1;
        }

        if (language.key === "chinese") {
            const chineseCharacters = (line.match(/[\u4E00-\u9FFF]/g) || []).length;
            const japaneseKana = /[\u3040-\u30ff]/.test(line);

            return chineseCharacters >= 2 && !japaneseKana;
        }

        if (language.key === "japanese") {
            return /[\u3040-\u30ff]/.test(line) || (line.match(/[\u4E00-\u9FFF]/g) || []).length >= 2;
        }

        return language.textPattern.test(line);
    }

    function extractLanguageSnippetFromLine(line, language) {
        const cleanedLine = String(line || "")
            .replace(/^.*?(音声(?:用)?|再生用|読み上げ用|Audio)\s*[:：]\s*/i, "")
            .replace(/^[\s"'“”‘’「『（(]*(?:[A-DＡ-Ｄ]|[ア-エ]|[0-9０-９]+|Q|Question|問|問題)\s*[:：.)．、]\s*/i, "")
            .trim();

        if (!cleanedLine) {
            return "";
        }

        if (language.key === "english") {
            const englishChunks = cleanedLine.match(/[A-Za-z][A-Za-z'’-]*(?:[\s,.!?;:]+[A-Za-z][A-Za-z'’-]*)*/g) || [];
            return englishChunks.join(" ").replace(/\s+/g, " ").trim();
        }

        if (language.key === "korean") {
            const koreanChunks = cleanedLine.match(/[\u1100-\u11FF\u3130-\u318F\uAC00-\uD7AF\uA960-\uA97F\uD7B0-\uD7FF][\u1100-\u11FF\u3130-\u318F\uAC00-\uD7AF\uA960-\uA97F\uD7B0-\uD7FF\s,.!?！？。]*/g) || [];
            return koreanChunks.join(" ").replace(/\s+/g, " ").trim();
        }

        if (language.key === "chinese") {
            const chineseChunks = cleanedLine
                .match(/[\u4E00-\u9FFF][\u4E00-\u9FFF\s，。！？,.!?]*/g) || [];
            return chineseChunks
                .map(function (chunk) {
                    return chunk.trim();
                })
                .filter(function (chunk) {
                    return chunk.length >= 2 && !/^(中国語|中文|漢字)$/.test(chunk);
                })
                .join(" ")
                .trim();
        }

        return cleanedLine;
    }

    function extractLanguageAudioText(text, language, contextLabel, sourceType) {
        const value = String(text || "");
        const context = String(contextLabel || "");
        const hasManualRequest = LANGUAGE_AUDIO_MANUAL_REQUEST_PATTERN.test(value);
        const contextIsExerciseSection = sourceType === "textbook"
            ? LANGUAGE_AUDIO_TEXTBOOK_SECTION_PATTERN.test(context)
            : LANGUAGE_AUDIO_SECTION_PATTERN.test(context);
        const rawLines = value
            .split("\n")
            .map(function (line) {
                return line.trim();
            })
            .filter(Boolean);
        const manualMarkerIndex = rawLines.findIndex(function (line) {
            return LANGUAGE_AUDIO_MANUAL_REQUEST_PATTERN.test(line);
        });
        const lines = rawLines
            .filter(function (line, index) {
                if (!line) {
                    return false;
                }

                if (/^(@|def |class |return |import |from |const |let |var |function |\{|\}|\/\/|#)/.test(line)) {
                    return false;
                }

                if (!lineMatchesLanguage(line, language) && !(sourceType === "chat" && language.textPattern.test(line))) {
                    return false;
                }

                if (sourceType === "selection") {
                    return true;
                }

                if (sourceType === "chat") {
                    if (!hasManualRequest) {
                        return false;
                    }
                    if (manualMarkerIndex >= 0 && index < manualMarkerIndex) {
                        return false;
                    }
                } else if (!contextIsExerciseSection) {
                    const nearbyInstruction = [
                        rawLines[index - 2] || "",
                        rawLines[index - 1] || "",
                        line
                    ].join(" ");

                    if (!hasLanguageAudioMarker(nearbyInstruction)) {
                        return false;
                    }
                }

                return true;
            })
            .map(function (line) {
                return extractLanguageSnippetFromLine(line, language);
            })
            .filter(Boolean);

        return normalizeLanguageAudioPlaybackText(lines, language).slice(0, 1800);
    }

    function normalizeLanguageAudioPlaybackText(lines, language) {
        const values = (Array.isArray(lines) ? lines : [lines])
            .map(function (line) {
                return String(line || "").replace(/[ \t]+/g, " ").trim();
            })
            .filter(Boolean);

        if (!values.length) {
            return "";
        }

        if (language.key === "english") {
            return values
                .map(function (line) {
                    return line.replace(/\s+([,.!?;:])/g, "$1").trim();
                })
                .join("\n")
                .trim();
        }

        return values.join("\n").trim();
    }

    function splitLanguageSentences(text, language) {
        const value = String(text || "").trim();

        if (!value) {
            return [];
        }

        const sentencePattern = language.key === "english"
            ? /[^.!?\n]+[.!?]?/g
            : /[^。！？.!?\n]+[。！？.!?]?/g;
        const sentences = value
            .split(/\n+/)
            .flatMap(function (line) {
                const trimmedLine = line.trim();
                return trimmedLine.match(sentencePattern) || (trimmedLine ? [trimmedLine] : []);
            });

        return sentences
            .map(function (sentence) {
                return sentence.trim();
            })
            .filter(Boolean)
            .slice(0, 20);
    }

    function buildSpeechSegments(text, language) {
        const value = String(text || "").replace(/\r/g, "").trim();

        if (!value) {
            return [];
        }

        const lines = value
            .split(/\n+/)
            .map(function (line) {
                return line.trim();
            })
            .filter(Boolean);
        const segments = [];

        lines.forEach(function (line, lineIndex) {
            const parts = language.key === "english"
                ? line.split(/,\s*/).map(function (part) {
                    return part.trim();
                }).filter(Boolean)
                : [line];

            parts.forEach(function (part, partIndex) {
                const isLastPartInLine = partIndex === parts.length - 1;
                const isLastLine = lineIndex === lines.length - 1;
                const pauseAfter = !isLastPartInLine
                    ? 260
                    : !isLastLine
                        ? 520
                        : 0;

                segments.push({
                    text: part,
                    pauseAfter: pauseAfter
                });
            });
        });

        return segments;
    }

    function normalizeAnswerText(text, language) {
        const value = String(text || "").toLowerCase();

        if (language.key === "english") {
            return value.replace(/[^a-z0-9\s']/g, "").replace(/\s+/g, " ").trim();
        }

        return value.replace(/[\s、。！？,.!?「」『』（）()]/g, "").trim();
    }

    function calculateSimilarityScore(expected, actual, language) {
        const a = normalizeAnswerText(expected, language);
        const b = normalizeAnswerText(actual, language);
        const maxLength = Math.max(a.length, b.length);

        if (!maxLength) {
            return 0;
        }

        const rows = Array.from({ length: a.length + 1 }, function () {
            return new Array(b.length + 1).fill(0);
        });

        for (let i = 0; i <= a.length; i += 1) {
            rows[i][0] = i;
        }

        for (let j = 0; j <= b.length; j += 1) {
            rows[0][j] = j;
        }

        for (let i = 1; i <= a.length; i += 1) {
            for (let j = 1; j <= b.length; j += 1) {
                const cost = a[i - 1] === b[j - 1] ? 0 : 1;
                rows[i][j] = Math.min(
                    rows[i - 1][j] + 1,
                    rows[i][j - 1] + 1,
                    rows[i - 1][j - 1] + cost
                );
            }
        }

        return Math.max(0, Math.round((1 - rows[a.length][b.length] / maxLength) * 100));
    }

    function buildPracticeFeedback(score) {
        if (score >= 90) {
            return "かなり近いです。この調子で自然に言えるまで続けましょう。";
        }

        if (score >= 70) {
            return "だいぶ合っています。聞こえた順番と細かい語尾をもう一度確認しましょう。";
        }

        if (score >= 45) {
            return "一部は合っています。まずは短い一文だけに絞ると練習しやすいです。";
        }

        return "まだ差があります。音声をもう一度聞いて、最初の数語から真似してみましょう。";
    }

    function LanguageAudioTools(props) {
        const text = props.text || "";
        const contextLabel = props.contextLabel || "";
        const label = props.label || "音声";
        const sourceType = props.sourceType || "auto";
        const [status, setStatus] = useState("idle");
        const [rate, setRate] = useState("1");
        const [error, setError] = useState("");
        const [sentenceIndex, setSentenceIndex] = useState(0);
        const [practiceMode, setPracticeMode] = useState("");
        const [dictationAnswer, setDictationAnswer] = useState("");
        const [practiceResult, setPracticeResult] = useState("");
        const [recognitionStatus, setRecognitionStatus] = useState("idle");
        const audioIdRef = useRef(`language-audio-${Math.random().toString(36).slice(2)}`);
        const playbackTokenRef = useRef(0);
        const playbackTimerRef = useRef(null);
        const recognitionRef = useRef(null);
        const target = detectLanguageTarget(text, contextLabel, sourceType);

        useEffect(function () {
            setSentenceIndex(0);
        }, [target ? target.text : ""]);

        useEffect(function () {
            function handleAudioStart(event) {
                if (!event.detail || event.detail.id !== audioIdRef.current) {
                    setStatus("idle");
                }
            }

            function handleAudioStop() {
                setStatus("idle");
            }

            window.addEventListener("pas-language-audio-start", handleAudioStart);
            window.addEventListener("pas-language-audio-stop", handleAudioStop);

            return function () {
                window.removeEventListener("pas-language-audio-start", handleAudioStart);
                window.removeEventListener("pas-language-audio-stop", handleAudioStop);

                if (recognitionRef.current) {
                    try {
                        recognitionRef.current.stop();
                    } catch (err) {
                        recognitionRef.current = null;
                    }
                }

                if (playbackTimerRef.current) {
                    window.clearTimeout(playbackTimerRef.current);
                    playbackTimerRef.current = null;
                }
            };
        }, []);

        if (!target || !isSpeechAvailable()) {
            return null;
        }

        const activeSentence = target.sentences[Math.min(sentenceIndex, target.sentences.length - 1)] || target.text;
        const canUseRecognition = Boolean(getSpeechRecognitionConstructor());
        const showPracticeTools = sourceType === "textbook";
        const sentenceCount = target.sentences.length;
        const hasMultipleSentences = sentenceCount > 1;
        const currentSentenceNumber = sentenceCount ? Math.min(sentenceIndex + 1, sentenceCount) : 1;

        function stopAudio() {
            playbackTokenRef.current += 1;
            if (playbackTimerRef.current) {
                window.clearTimeout(playbackTimerRef.current);
                playbackTimerRef.current = null;
            }
            window.speechSynthesis.cancel();
            setStatus("idle");
            window.dispatchEvent(new CustomEvent("pas-language-audio-stop"));
        }

        function playAudio(speechText) {
            if (!speechText) {
                setError("再生できる文章が見つかりませんでした。");
                return;
            }

            const segments = buildSpeechSegments(speechText, target.language);

            if (!segments.length) {
                setError("再生できる文章が見つかりませんでした。");
                return;
            }

            setError("");
            playbackTokenRef.current += 1;
            const playbackToken = playbackTokenRef.current;
            if (playbackTimerRef.current) {
                window.clearTimeout(playbackTimerRef.current);
                playbackTimerRef.current = null;
            }
            window.speechSynthesis.cancel();
            if (window.speechSynthesis.paused) {
                window.speechSynthesis.resume();
            }
            window.dispatchEvent(
                new CustomEvent("pas-language-audio-start", {
                    detail: { id: audioIdRef.current }
                })
            );

            const voices = window.speechSynthesis.getVoices ? window.speechSynthesis.getVoices() : [];
            const matchingVoice = voices.find(function (voice) {
                return voice.lang && voice.lang.toLowerCase().startsWith(target.language.lang.slice(0, 2).toLowerCase());
            });
            let segmentIndex = 0;
            setStatus("loading");

            function speakNextSegment() {
                if (playbackTokenRef.current !== playbackToken) {
                    return;
                }

                const segment = segments[segmentIndex];

                if (!segment) {
                    setStatus("idle");
                    return;
                }

                const utterance = new SpeechSynthesisUtterance(segment.text);
                utterance.lang = target.language.lang;

                if (matchingVoice) {
                    utterance.voice = matchingVoice;
                }

                utterance.rate = Number(rate);
                utterance.onstart = function () {
                    if (playbackTokenRef.current === playbackToken) {
                        setStatus("playing");
                    }
                };
                utterance.onend = function () {
                    if (playbackTokenRef.current !== playbackToken) {
                        return;
                    }

                    segmentIndex += 1;

                    if (segmentIndex >= segments.length) {
                        setStatus("idle");
                        return;
                    }

                    playbackTimerRef.current = window.setTimeout(speakNextSegment, segment.pauseAfter);
                };
                utterance.onerror = function () {
                    if (playbackTokenRef.current !== playbackToken) {
                        return;
                    }

                    setStatus("idle");
                    setError("音声を再生できませんでした。もう一度試してください。");
                };

                window.speechSynthesis.speak(utterance);
            }

            speakNextSegment();
        }

        function playSentenceAt(index) {
            const safeIndex = target.sentences.length
                ? Math.max(0, Math.min(index, target.sentences.length - 1))
                : 0;
            setSentenceIndex(safeIndex);
            playAudio(target.sentences[safeIndex] || target.text);
        }

        function playFirstSentence() {
            playSentenceAt(0);
        }

        function playPreviousSentence() {
            playSentenceAt(sentenceIndex - 1);
        }

        function playCurrentSentence() {
            playSentenceAt(sentenceIndex);
        }

        function playNextSentence() {
            playSentenceAt(sentenceIndex + 1);
        }

        function checkDictation() {
            const score = calculateSimilarityScore(activeSentence, dictationAnswer, target.language);
            setPracticeResult(`一致度 ${score}%：${buildPracticeFeedback(score)}`);
        }

        function startPronunciationCheck() {
            const Recognition = getSpeechRecognitionConstructor();

            if (!Recognition) {
                setPracticeResult("このブラウザでは発音チェックに必要な音声認識が使えません。ChromeやSafariの対応環境で試してください。");
                return;
            }

            if (recognitionRef.current) {
                try {
                    recognitionRef.current.stop();
                } catch (err) {
                    recognitionRef.current = null;
                }
            }

            const recognition = new Recognition();
            recognition.lang = target.language.lang;
            recognition.interimResults = false;
            recognition.maxAlternatives = 1;
            recognitionRef.current = recognition;
            setRecognitionStatus("listening");
            setPracticeResult("聞き取り中です。上の文を声に出して読んでください。");

            recognition.onresult = function (event) {
                const transcript = event.results && event.results[0] && event.results[0][0]
                    ? event.results[0][0].transcript
                    : "";
                const score = calculateSimilarityScore(activeSentence, transcript, target.language);
                setRecognitionStatus("idle");
                setPracticeResult(`聞き取り: ${transcript || "取得できませんでした"} / 発音一致度 ${score}%：${buildPracticeFeedback(score)}`);
            };

            recognition.onerror = function () {
                setRecognitionStatus("idle");
                setPracticeResult("音声をうまく聞き取れませんでした。マイク許可と周囲の音を確認してください。");
            };

            recognition.onend = function () {
                setRecognitionStatus("idle");
            };

            recognition.start();
        }

        return h(
            "div",
            { className: `language-audio-tools language-audio-${sourceType}` },
            h(
                "button",
                {
                    type: "button",
                    className: "audio-play-button",
                    onClick: status === "playing" || status === "loading" ? stopAudio : function () {
                        playAudio(target.text);
                    },
                    "aria-label": status === "playing" || status === "loading" ? `${target.language.label}音声を停止` : `${target.language.label}音声を再生`
                },
                status === "loading" ? "読み込み中" : status === "playing" ? "停止" : label
            ),
            h(
                "div",
                { className: "audio-sequence-controls" },
                hasMultipleSentences
                    ? h(
                        "button",
                        {
                            type: "button",
                            className: "audio-play-button secondary-audio-button",
                            onClick: playFirstSentence
                        },
                        "最初"
                    )
                    : null,
                hasMultipleSentences
                    ? h(
                        "button",
                        {
                            type: "button",
                            className: "audio-play-button secondary-audio-button",
                            onClick: playPreviousSentence,
                            disabled: sentenceIndex <= 0
                        },
                        "前へ"
                    )
                    : null,
                h(
                    "button",
                    {
                        type: "button",
                        className: "audio-play-button secondary-audio-button",
                        onClick: playCurrentSentence
                    },
                    "一文"
                ),
                hasMultipleSentences
                    ? h(
                        "button",
                        {
                            type: "button",
                            className: "audio-play-button secondary-audio-button",
                            onClick: playNextSentence,
                            disabled: sentenceIndex >= sentenceCount - 1
                        },
                        "次へ"
                    )
                    : null,
                hasMultipleSentences
                    ? h(
                        "select",
                        {
                            className: "audio-sentence-select",
                            value: String(sentenceIndex),
                            onChange: function (event) {
                                playSentenceAt(Number(event.target.value));
                            },
                            "aria-label": "聞く文を選ぶ"
                        },
                        target.sentences.map(function (sentence, index) {
                            return h(
                                "option",
                                { key: `${index}-${sentence.slice(0, 12)}`, value: String(index) },
                                `${index + 1}文目`
                            );
                        })
                    )
                    : null,
                hasMultipleSentences
                    ? h(
                        "span",
                        { className: "audio-position-label" },
                        `${currentSentenceNumber}/${sentenceCount}`
                    )
                    : null
            ),
            h(
                "select",
                {
                    className: "audio-rate-select",
                    value: rate,
                    onChange: function (event) {
                        setRate(event.target.value);
                    },
                    "aria-label": "再生速度"
                },
                h("option", { value: "0.75" }, "0.75x"),
                h("option", { value: "1" }, "1.0x"),
                h("option", { value: "1.25" }, "1.25x")
            ),
            h("span", { className: "language-audio-label" }, target.language.label),
            showPracticeTools
                ? h(
                    "div",
                    { className: "language-practice-actions" },
                    h(
                        "button",
                        {
                            type: "button",
                            onClick: function () {
                                setPracticeMode(practiceMode === "shadowing" ? "" : "shadowing");
                                setPracticeResult("");
                            }
                        },
                        "シャドーイング"
                    ),
                    h(
                        "button",
                        {
                            type: "button",
                            onClick: function () {
                                setPracticeMode(practiceMode === "dictation" ? "" : "dictation");
                                setPracticeResult("");
                            }
                        },
                        "ディクテーション"
                    ),
                    h(
                        "button",
                        {
                            type: "button",
                            onClick: function () {
                                setPracticeMode(practiceMode === "pronunciation" ? "" : "pronunciation");
                                setPracticeResult("");
                            }
                        },
                        "発音チェック"
                    )
                )
                : null,
            showPracticeTools && practiceMode
                ? h(
                    "div",
                    { className: "language-practice-panel" },
                    h("p", { className: "practice-target" }, activeSentence),
                    practiceMode === "shadowing"
                        ? h("p", null, "音声を聞いたあと、同じリズムで声に出して練習してください。")
                        : null,
                    practiceMode === "dictation"
                        ? h(
                            React.Fragment,
                            null,
                            h("textarea", {
                                value: dictationAnswer,
                                onChange: function (event) {
                                    setDictationAnswer(event.target.value);
                                },
                                placeholder: "聞こえた内容を書いてください"
                            }),
                            h(
                                "button",
                                { type: "button", onClick: checkDictation },
                                "答え合わせ"
                            )
                        )
                        : null,
                    practiceMode === "pronunciation"
                        ? h(
                            "button",
                            {
                                type: "button",
                                onClick: startPronunciationCheck,
                                disabled: recognitionStatus === "listening"
                            },
                            recognitionStatus === "listening" ? "聞き取り中" : canUseRecognition ? "声に出して評価" : "音声認識は未対応"
                        )
                        : null,
                    practiceResult ? h("p", { className: "practice-result" }, practiceResult) : null
                )
                : null,
            error ? h("p", { className: "audio-error" }, error) : null
        );
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
        } else if (route === "/roadmaps") {
            screen = h(RoadmapsScreen, { navigate });
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
                        h(
                            "button",
                            {
                                type: "button",
                                onClick: function () {
                                    navigate("/roadmaps", { message: "ロードマップを開いています" });
                                }
                            },
                            "ロードマップ"
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

    function RoadmapsScreen({ navigate }) {
        const [data, setData] = useState(null);
        const [error, setError] = useState("");
        const [deletingKey, setDeletingKey] = useState("");

        function loadRoadmaps(activeRef) {
            api("/api/roadmaps")
                .then(function (response) {
                    if (!activeRef || activeRef.active) {
                        setData(response);
                    }
                })
                .catch(function () {
                    if (!activeRef || activeRef.active) {
                        setError("ロードマップを読み込めませんでした。");
                    }
                });
        }

        useEffect(function () {
            const activeRef = { active: true };

            loadRoadmaps(activeRef);

            return function () {
                activeRef.active = false;
            };
        }, []);

        const subjects = data ? data.subjects || [] : [];
        const statusLabels = {
            learned: "理解済み",
            learning: "学習中",
            review: "復習",
            not_started: "未学習",
            skipped: "飛ばした単元"
        };

        function openSubjectLesson(subject) {
            if (subject.chat_url) {
                navigate(subject.chat_url, { message: `${subject.subject}の授業を準備しています` });
                return;
            }

            navigate(subject.bookshelf_url, { message: "本棚を開いています" });
        }

        async function deleteRoadmap(subject) {
            const currentItem = subject.current_item ? `現在地「${subject.current_item.title}」` : "現在地";
            const nextItem = subject.next_item ? `次のおすすめ「${subject.next_item.title}」` : "次のおすすめ";
            const confirmed = window.confirm(
                `${subject.roadmap_title || subject.subject}を削除しますか？\n\n削除すると、学習目標・${currentItem}・進捗・${nextItem}・AIが参照しているロードマップ情報もMemoryから外します。\n\n教科書・理解度・添削結果は残ります。`
            );

            if (!confirmed) {
                return;
            }

            setDeletingKey(subject.subject);
            setError("");

            try {
                await api("/api/roadmaps", {
                    method: "DELETE",
                    body: JSON.stringify({
                        subject: subject.subject,
                        thread_id: subject.thread_id || null
                    })
                });
                setData(function (currentData) {
                    const currentSubjects = currentData && currentData.subjects ? currentData.subjects : [];

                    return {
                        subjects: currentSubjects.filter(function (item) {
                            return item.subject !== subject.subject;
                        })
                    };
                });
            } catch (err) {
                setError("ロードマップを削除できませんでした。もう一度試してください。");
            } finally {
                setDeletingKey("");
            }
        }

        return h(
            "main",
            { className: "study-app study-library roadmap-page" },
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
                    { className: "library-title-block" },
                    h("p", { className: "eyebrow" }, "Roadmap"),
                    h("h1", null, "学習ロードマップ")
                ),
                h("span", null)
            ),
            h(
                "section",
                { className: "library-intro roadmap-intro" },
                h("p", { className: "section-kicker" }, "同じ地図を見る"),
                h("h2", null, "先生と同じロードマップで、今いる場所を確認する。"),
                h("p", null, "順番はおすすめです。好きな教材や単元から始めても、先生が必要な前提知識を補いながら進めます。")
            ),
            error ? h("p", { className: "notice" }, error) : null,
            !data
                ? h("p", { className: "react-loading" }, "読み込み中")
                : subjects.length
                    ? h(
                        "section",
                        { className: "roadmap-overview-list" },
                        subjects.map(function (subject) {
                            return h(
                                "article",
                                { key: `${subject.subject}-${subject.thread_id || "global"}`, className: "roadmap-subject-card" },
                                (function () {
                                    const total = subject.total_count || (subject.items ? subject.items.length : 0);
                                    const completed = subject.completed_count || 0;
                                    const progress = total ? Math.round((completed / total) * 100) : (subject.understanding_percent || 0);
                                    const currentTitle = subject.current_item ? subject.current_item.title : "まだ未設定";
                                    const nextTitle = subject.next_item ? subject.next_item.title : "先生と相談して決める";

                                    return h(
                                        React.Fragment,
                                        null,
                                        h(
                                            "div",
                                            { className: "roadmap-subject-head" },
                                            h(
                                                "div",
                                                null,
                                                h("p", { className: "section-kicker" }, "教材ロードマップ"),
                                                h("h2", null, subject.roadmap_title || subject.subject),
                                                h("small", null, subject.subject)
                                            ),
                                            h(
                                                "button",
                                                {
                                                    type: "button",
                                                    onClick: function () {
                                                        openSubjectLesson(subject);
                                                    }
                                                },
                                                "授業へ"
                                            ),
                                            h(
                                                "button",
                                                {
                                                    type: "button",
                                                    className: "roadmap-delete-button",
                                                    disabled: deletingKey === subject.subject,
                                                    onClick: function () {
                                                        deleteRoadmap(subject);
                                                    }
                                                },
                                                deletingKey === subject.subject ? h(LoadingLabel, { text: "削除中" }) : "削除"
                                            )
                                        ),
                                        h(
                                            "section",
                                            { className: "roadmap-current-panel" },
                                            h("p", { className: "section-kicker" }, "現在地"),
                                            h("h3", null, currentTitle),
                                            h(
                                                "div",
                                                { className: "roadmap-current-grid" },
                                                h(
                                                    "span",
                                                    null,
                                                    h("small", null, "次におすすめ"),
                                                    h("strong", null, nextTitle)
                                                ),
                                                h(
                                                    "span",
                                                    null,
                                                    h("small", null, "進捗"),
                                                    h("strong", null, `${progress}%`)
                                                )
                                            ),
                                            h(
                                                "div",
                                                { className: "roadmap-progress-track", "aria-label": `進捗 ${progress}%` },
                                                h("i", { style: { width: `${Math.min(100, Math.max(0, progress))}%` } })
                                            )
                                        )
                                    );
                                })(),
                                subject.goal
                                    ? h("p", { className: "roadmap-goal-text" }, `目標: ${subject.goal}`)
                                    : null,
                                h(
                                    "div",
                                    { className: "roadmap-summary-pills" },
                                    h("span", null, `理解度 ${subject.understanding_percent || 0}%`),
                                    h("span", null, `完了 ${subject.completed_count || 0}/${subject.total_count || 0}`),
                                    h("span", null, subject.current_item ? `現在地 ${subject.current_item.title}` : "現在地 未設定"),
                                    h("span", null, subject.next_item ? `次の候補 ${subject.next_item.title}` : "次の候補なし"),
                                    subject.latest_updated_at ? h("span", null, `更新 ${subject.latest_updated_at}`) : null
                                ),
                                h(
                                    "div",
                                    { className: "roadmap-materials" },
                                    h("h3", null, "教材"),
                                    subject.textbooks && subject.textbooks.length
                                        ? h(
                                            "div",
                                            { className: "material-list" },
                                            subject.textbooks.map(function (textbook) {
                                                return h(
                                                    "button",
                                                    {
                                                        key: textbook.id,
                                                        type: "button",
                                                        className: "material-card",
                                                        onClick: function () {
                                                            navigate(textbook.url, { message: "教材を開いています" });
                                                        }
                                                    },
                                                    h("strong", null, textbook.title),
                                                    h("small", null, `更新 ${textbook.updated_at || "-"}`)
                                                );
                                            })
                                        )
                                        : h("p", { className: "roadmap-empty-text" }, "この分野の教材はまだありません。授業から教科書を作るとここに並びます。")
                                ),
                                h(
                                    "div",
                                    { className: "roadmap-map" },
                                    h("h3", null, "AIが見ている地図"),
                                    h(
                                        "div",
                                        { className: "roadmap-list" },
                                        subject.items.map(function (item, index) {
                                            return h(
                                                "button",
                                                {
                                                    key: item.id || `${subject.subject}-${item.title}`,
                                                    type: "button",
                                                    className: `roadmap-item roadmap-${item.status || "not_started"}`,
                                                    onClick: function () {
                                                        openSubjectLesson(subject);
                                                    }
                                                },
                                                h("span", { className: "roadmap-step-number" }, String(index + 1).padStart(2, "0")),
                                                    h(
                                                        "span",
                                                        { className: "roadmap-item-body" },
                                                        h("strong", null, item.title),
                                                        h("small", null, item.reason || "この順番で進むと理解しやすくなります。"),
                                                        typeof item.understanding_percent === "number" && item.understanding_percent > 0
                                                            ? h("small", null, `理解度 ${item.understanding_percent}%`)
                                                            : null
                                                    ),
                                                h("em", null, statusLabels[item.status] || "未学習")
                                            );
                                        })
                                    )
                                )
                            );
                        })
                    )
                    : h(
                        "section",
                        { className: "study-empty" },
                        h("p", null, "まだロードマップはありません。授業で「ロードマップを作って」と頼むと、ここに表示されます。")
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
                    { className: "library-title-block" },
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
                    { className: "library-title-block" },
                    h("p", { className: "eyebrow" }, "Bookshelf"),
                    h("h1", null, subject || "本棚")
                ),
                h("span", null)
            ),
            error ? h("p", { className: "notice" }, error) : null,
            !data
                ? h("p", { className: "react-loading" }, "読み込み中")
                : h(
                    React.Fragment,
                    null,
                    textbooks.length
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
                )
        );
    }

    function TextbookScreen({ route, navigate }) {
        const textbookIdMatch = route.match(/^\/textbook\/(\d+)/);
        const textbookId = textbookIdMatch ? textbookIdMatch[1] : "";
        const [data, setData] = useState(null);
        const [error, setError] = useState("");
        const [answerType, setAnswerType] = useState("check");
        const [answerText, setAnswerText] = useState("");
        const [usedHint, setUsedHint] = useState(false);
        const [submittingAnswer, setSubmittingAnswer] = useState(false);
        const [latestAssessment, setLatestAssessment] = useState(null);
        const readingScrollRef = useRef(0);

        useEffect(function () {
            let active = true;
            setData(null);
            setError("");
            setAnswerText("");
            setUsedHint(false);
            setLatestAssessment(null);

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

        async function submitTextbookAnswer(event) {
            event.preventDefault();

            const cleanAnswer = answerText.trim();

            if (!cleanAnswer || submittingAnswer || !textbook) {
                return;
            }

            setSubmittingAnswer(true);
            setError("");

            try {
                if (answerType === "question") {
                    await api(`/api/chat/${textbook.thread_id}/messages`, {
                        method: "POST",
                        body: JSON.stringify({
                            message: `教科書「${textbook.title}」について質問です。\n\n${cleanAnswer}`
                        })
                    });

                    setAnswerText("");
                    navigate(`/chat/${textbook.thread_id}`, { message: "先生に質問しています" });
                    return;
                }

                const response = await api(`/api/textbooks/${textbook.id}/answers`, {
                    method: "POST",
                    body: JSON.stringify({
                        answer_type: answerType,
                        answer_text: cleanAnswer,
                        used_hint: usedHint
                    })
                });

                if (response) {
                    setData({ textbook: response.textbook });
                    setLatestAssessment(response.assessment);
                    setAnswerText("");
                    setUsedHint(false);
                    window.setTimeout(function () {
                        const result = document.querySelector(".assessment-result-card");
                        if (result) {
                            result.scrollIntoView({ behavior: "smooth", block: "nearest" });
                        }
                    }, 80);
                }
            } catch (err) {
                setError(answerType === "question"
                    ? "質問を送信できませんでした。もう一度試してください。"
                    : "回答を添削できませんでした。もう一度試してください。");
            } finally {
                setSubmittingAnswer(false);
            }
        }

        function startReview(suggestion) {
            setAnswerType("review");
            setAnswerText(`復習する内容: ${suggestion.item_name}\n\n自分の回答:\n`);
            window.setTimeout(function () {
                const form = document.querySelector(".answer-submit-card");
                if (form) {
                    form.scrollIntoView({ behavior: "smooth", block: "nearest" });
                }
            }, 80);
        }

        function rememberReadingScroll() {
            readingScrollRef.current = window.scrollY;
        }

        function restoreReadingScroll() {
            const scrollTop = readingScrollRef.current;

            if (!scrollTop && scrollTop !== 0) {
                return;
            }

            window.setTimeout(function () {
                window.scrollTo({ top: scrollTop, behavior: "auto" });
            }, 40);
        }

        const textbook = data ? data.textbook : null;
        const sections = textbook ? textbook.sections.filter(function (section) {
            return section.content && section.content.trim();
        }) : [];
        const understandings = textbook ? textbook.understandings || [] : [];
        const subjectUnderstanding = understandings.find(function (item) {
            return item.scope_type === "subject";
        });
        const textbookUnderstanding = understandings.find(function (item) {
            return item.scope_type === "textbook";
        });
        const itemUnderstandings = understandings.filter(function (item) {
            return item.scope_type === "item";
        });
        const assessments = textbook ? textbook.assessments || [] : [];
        const reviewSuggestions = textbook ? textbook.review_suggestions || [] : [];
        const currentProblemText = getCurrentProblemText();
        const answerCardKicker = answerType === "question" ? "先生に質問する" : "問題に回答する";
        const answerCardTitle = answerType === "question"
            ? "教科書を見ながら分からないところを聞く"
            : "解いた答えを先生に添削してもらう";
        const answerPlaceholder = answerType === "question"
            ? "分からないところをそのまま質問してください。例: 2番の問題で、なぜこの式になるのか分かりません。"
            : "ここに自分の回答を書いてください。途中式や考え方も書くと、先生がより正確に添削できます。";
        const submitLabel = answerType === "question" ? "先生に質問する" : "回答を提出する";
        const loadingLabel = answerType === "question" ? "質問中" : "添削中";
        const showHintCheck = answerType !== "question";

        function findSectionContent(sectionKey) {
            if (!textbook || !textbook.sections) {
                return "";
            }

            const section = textbook.sections.find(function (item) {
                return item.key === sectionKey;
            });

            return section && section.content ? normalizeTextbookSectionContent(section.content) : "";
        }

        function getCurrentProblemText() {
            if (!textbook) {
                return "";
            }

            if (answerType === "check") {
                return findSectionContent("check_questions") || "理解確認問題がまだありません。教科書本文を読んで、自分の言葉で要点を書いてみてください。";
            }

            if (answerType === "application") {
                return findSectionContent("application_questions") || "応用問題がまだありません。学んだ内容を別の例で使うならどうなるかを書いてみてください。";
            }

            if (answerType === "review") {
                if (reviewSuggestions.length) {
                    return reviewSuggestions.map(function (suggestion, index) {
                        return `${index + 1}. ${suggestion.item_name}\n${suggestion.review_message}`;
                    }).join("\n\n");
                }

                return findSectionContent("key_points") || findSectionContent("personal_points") || "次に復習したい内容を選んで、自分の言葉で説明してみてください。";
            }

            return `教科書「${textbook.title}」を見ながら、分からないところを先生に質問できます。問題番号、本文の場所、つまずいた理由を書けると、先生が答えやすくなります。`;
        }

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
                    { className: "textbook-title-block" },
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
                        "section",
                        { className: "understanding-panel" },
                        h("p", { className: "section-kicker" }, "理解度"),
                        h(
                            "div",
                            { className: "understanding-summary" },
                            h(
                                "div",
                                null,
                                h("span", null, `${textbook.subject}全体`),
                                h("strong", null, `${subjectUnderstanding ? subjectUnderstanding.percent : 0}%`),
                                h("small", null, subjectUnderstanding ? `変化 ${subjectUnderstanding.delta_percent >= 0 ? "+" : ""}${subjectUnderstanding.delta_percent}%` : "まだ未測定")
                            ),
                            h(
                                "div",
                                null,
                                h("span", null, "この教科書"),
                                h("strong", null, `${textbookUnderstanding ? textbookUnderstanding.percent : 0}%`),
                                h("small", null, textbookUnderstanding ? `変化 ${textbookUnderstanding.delta_percent >= 0 ? "+" : ""}${textbookUnderstanding.delta_percent}%` : "回答すると更新")
                            )
                        ),
                        itemUnderstandings.length
                            ? h(
                                "div",
                                { className: "item-understanding-list" },
                                itemUnderstandings.map(function (item) {
                                    return h(
                                        "div",
                                        { key: item.id, className: "item-understanding" },
                                        h("span", null, item.item_name),
                                        h("strong", null, `${item.percent}%`),
                                        h("small", null, `${item.delta_percent >= 0 ? "+" : ""}${item.delta_percent}%`)
                                    );
                                })
                            )
                            : h("p", { className: "understanding-empty" }, "問題に回答すると、項目ごとの理解度が表示されます。")
                    ),
                    h(
                        "section",
                        { className: "review-plan-card" },
                        h("p", { className: "section-kicker" }, "復習提案"),
                        h("h2", null, reviewSuggestions.length ? "今やると定着しやすい復習" : "次の復習を待っています"),
                        reviewSuggestions.length
                            ? h(
                                "div",
                                { className: "review-suggestion-list" },
                                reviewSuggestions.map(function (suggestion) {
                                    return h(
                                        "article",
                                        { key: `${suggestion.scope_type}-${suggestion.id}` },
                                        h(
                                            "div",
                                            null,
                                            h("strong", null, suggestion.item_name),
                                            h("small", null, `${suggestion.percent}% / ${suggestion.review_message}`)
                                        ),
                                        h(
                                            "button",
                                            {
                                                type: "button",
                                                onClick: function () {
                                                    startReview(suggestion);
                                                }
                                            },
                                            "復習する"
                                        )
                                    );
                                })
                            )
                            : h(
                                "p",
                                null,
                                textbookUnderstanding && textbookUnderstanding.next_review_at
                                    ? `次回の復習予定は ${textbookUnderstanding.next_review_at} です。`
                                    : "回答を提出すると、先生が次の復習タイミングを決めます。"
                            )
                    ),
                    sections.length
                        ? h(
                            "nav",
                            { className: "textbook-toc", "aria-label": "教科書の目次" },
                            h("p", { className: "section-kicker" }, "目次"),
                            h("h2", null, "この章で読むこと"),
                            h(
                                "div",
                                { className: "textbook-toc-list" },
                                sections.map(function (section, index) {
                                    return h(
                                        "button",
                                        {
                                            key: section.key,
                                            type: "button",
                                            onClick: function () {
                                                const target = document.getElementById(`textbook-section-${section.key}`);
                                                if (target) {
                                                    target.scrollIntoView({ behavior: "smooth", block: "start" });
                                                }
                                            }
                                        },
                                        h("span", null, String(index + 1).padStart(2, "0")),
                                        h("strong", null, section.label)
                                    );
                                })
                            )
                        )
                        : null,
                    h(
                        "article",
                        { className: "textbook-reader" },
                        sections.map(function (section, index) {
                            const blockSection = section.key === "code_example" || section.key === "visual_diagram";
                            const compactAudioSection = LANGUAGE_AUDIO_TEXTBOOK_SECTION_PATTERN.test(section.label || "");
                            const audioContext = `${textbook.subject || ""} ${textbook.title || ""} ${section.label || ""}`;
                            const displayContent = normalizeTextbookSectionContent(section.content, compactAudioSection);
                            const audioLines = compactAudioSection
                                ? displayContent.split("\n").filter(function (line) {
                                    return line.trim();
                                })
                                : [];

                            return h(
                                "section",
                                {
                                    key: section.key,
                                    id: `textbook-section-${section.key}`,
                                    className: `textbook-section${compactAudioSection ? " textbook-section-audio" : ""}`
                                },
                                h(
                                    "div",
                                    { className: "textbook-chapter-heading" },
                                    h("span", null, String(index + 1).padStart(2, "0")),
                                    h("h2", null, section.label)
                                ),
                                blockSection
                                    ? h(
                                        "pre",
                                        { className: section.key === "code_example" ? "textbook-code-block" : "textbook-diagram-block" },
                                        h("code", null, displayContent)
                                    )
                                    : h(
                                        React.Fragment,
                                        null,
                                        compactAudioSection
                                            ? h(
                                                "div",
                                                { className: "textbook-audio-lines" },
                                                audioLines.map(function (line, lineIndex) {
                                                    return h(
                                                        "p",
                                                        { key: `${section.key}-${lineIndex}`, className: "textbook-audio-line" },
                                                        line
                                                    );
                                                })
                                            )
                                            : h("p", null, displayContent),
                                        h(LanguageAudioTools, {
                                            text: displayContent,
                                            contextLabel: audioContext,
                                            label: "音声で聞く",
                                            sourceType: "textbook"
                                        })
                                    )
                            );
                        })
                    ),
                    latestAssessment
                        ? h(
                            "section",
                            { className: "assessment-result-card" },
                            h("p", { className: "section-kicker" }, "AI添削"),
                            h("h2", null, `今回の定着度 ${latestAssessment.score_percent}%`),
                            h("p", null, latestAssessment.feedback),
                            latestAssessment.understood_points
                                ? h("p", null, `理解できている点: ${latestAssessment.understood_points}`)
                                : null,
                            latestAssessment.weak_points
                                ? h("p", null, `苦手ポイント: ${latestAssessment.weak_points}`)
                                : null,
                            latestAssessment.next_review_content
                                ? h("p", null, `次に復習する内容: ${latestAssessment.next_review_content}`)
                                : null
                        )
                        : null,
                    h(
                        "section",
                        { className: "answer-submit-card" },
                        h("p", { className: "section-kicker" }, answerCardKicker),
                        h("h2", null, answerCardTitle),
                        h(
                            "div",
                            { className: "answer-type-tabs", role: "tablist" },
                            [
                                { key: "check", label: "理解確認" },
                                { key: "application", label: "応用問題" },
                                { key: "review", label: "復習" },
                                { key: "question", label: "質問" }
                            ].map(function (item) {
                                return h(
                                    "button",
                                    {
                                        key: item.key,
                                        type: "button",
                                        className: answerType === item.key ? "active" : "",
                                        onClick: function () {
                                            setAnswerType(item.key);
                                        }
                                    },
                                    item.label
                                );
                            })
                        ),
                        h(
                            "div",
                            { className: "answer-problem-preview" },
                            h("span", null, answerType === "question" ? "質問する内容" : "見ながら解く問題"),
                            h("pre", null, currentProblemText)
                        ),
                        h(
                            "form",
                            { className: "answer-form", onSubmit: submitTextbookAnswer },
                            h("textarea", {
                                value: answerText,
                                placeholder: answerPlaceholder,
                                onPointerDown: rememberReadingScroll,
                                onTouchStart: rememberReadingScroll,
                                onFocus: restoreReadingScroll,
                                onChange: function (event) {
                                    setAnswerText(event.target.value);
                                },
                                disabled: submittingAnswer
                            }),
                            showHintCheck ? h(
                                "label",
                                { className: "hint-check" },
                                h("input", {
                                    type: "checkbox",
                                    checked: usedHint,
                                    onChange: function (event) {
                                        setUsedHint(event.target.checked);
                                    },
                                    disabled: submittingAnswer
                                }),
                                "ヒントを使った"
                            ) : null,
                            h(
                                "button",
                                {
                                    type: "submit",
                                    disabled: submittingAnswer || !answerText.trim()
                                },
                                submittingAnswer ? h(LoadingLabel, { text: loadingLabel }) : submitLabel
                            )
                        )
                    ),
                    assessments.length
                        ? h(
                            "section",
                            { className: "assessment-history" },
                            h("h2", null, "最近の添削"),
                            assessments.map(function (assessment) {
                                return h(
                                    "article",
                                    { key: assessment.id },
                                    h("strong", null, `${assessment.score_percent}%`),
                                    h("span", null, assessment.created_at),
                                    h("p", null, assessment.feedback)
                                );
                            })
                        )
                        : null,
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
                        : null
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
        const abortControllerRef = useRef(null);
        const streamingAssistantRef = useRef("");
        const thinkingTimerRef = useRef(null);

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
                if (abortControllerRef.current) {
                    abortControllerRef.current.abort();
                    abortControllerRef.current = null;
                }
                stopThinkingLabels();
            };
        }, [apiPath]);

        useEffect(function () {
            window.requestAnimationFrame(function () {
                window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
            });
        }, [chatData, sending]);

        function updateStreamingAssistant(tempId, content) {
            setChatData(function (current) {
                if (!current) {
                    return current;
                }

                return {
                    ...current,
                    messages: current.messages.map(function (item) {
                        return item.temp_id === tempId
                            ? { ...item, content: content }
                            : item;
                    })
                };
            });
        }

        function stopThinkingLabels() {
            if (thinkingTimerRef.current) {
                window.clearInterval(thinkingTimerRef.current);
                thinkingTimerRef.current = null;
            }
        }

        function startThinkingLabels(labels) {
            let index = 0;
            const safeLabels = labels && labels.length ? labels : THINKING_LABELS;

            stopThinkingLabels();
            setSendingLabel(safeLabels[index]);

            thinkingTimerRef.current = window.setInterval(function () {
                index = (index + 1) % safeLabels.length;
                setSendingLabel(safeLabels[index]);
            }, 1400);
        }

        async function syncChatAfterStream() {
            if (!chatData) {
                return;
            }

            try {
                const data = await api(`/api/chat/${chatData.thread.id}`);

                if (data) {
                    setChatData(data);
                }
            } catch (err) {
                // 途中停止直後は保存が少し遅れることがあるため、画面上の途中回答を優先する。
            }
        }

        async function postTextMessage(cleanMessage, displayMessage) {
            if (!cleanMessage || !chatData || sending) {
                return;
            }

            const controller = new AbortController();
            const tempId = `stream-${Date.now()}`;
            abortControllerRef.current = controller;
            streamingAssistantRef.current = "";
            setSending(true);
            startThinkingLabels(THINKING_LABELS);
            setError("");
            setChatData({
                ...chatData,
                messages: chatData.messages.concat([
                    { role: "user", content: displayMessage || cleanMessage, created_at: "" },
                    { role: "assistant", content: "", created_at: "", temp_id: tempId }
                ])
            });
            setMessage("");

            try {
                await streamApi(`/api/chat/${chatData.thread.id}/messages/stream`, {
                    method: "POST",
                    body: JSON.stringify({ message: cleanMessage }),
                    signal: controller.signal
                }, function (eventName, data) {
                    if (eventName === "delta" && data.text) {
                        streamingAssistantRef.current += data.text;
                        updateStreamingAssistant(tempId, streamingAssistantRef.current);
                    }

                    if (eventName === "error" && data.message) {
                        setError(data.message);
                    }
                });
            } catch (err) {
                if (err.name !== "AbortError") {
                    setError("送信できませんでした。もう一度試してください。");
                }
            } finally {
                abortControllerRef.current = null;
                stopThinkingLabels();
                setSending(false);
                setSendingLabel("");
                window.setTimeout(syncChatAfterStream, 180);
            }
        }

        function stopGenerating() {
            if (!abortControllerRef.current) {
                return;
            }

            stopThinkingLabels();
            setSendingLabel("停止しています");
            abortControllerRef.current.abort();
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

            const controller = new AbortController();
            abortControllerRef.current = controller;
            setSending(true);
            startThinkingLabels(IMAGE_THINKING_LABELS);
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
                        body: formData,
                        signal: controller.signal
                    });
                } else {
                    data = await api(`/api/chat/${chatData.thread.id}/messages`, {
                        method: "POST",
                        body: JSON.stringify({ message: cleanMessage }),
                        signal: controller.signal
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
                if (err.name !== "AbortError") {
                    setError("送信できませんでした。もう一度試してください。");
                }
            } finally {
                abortControllerRef.current = null;
                stopThinkingLabels();
                setSending(false);
                setSendingLabel("");
            }
        }

        function sendLessonAction(action) {
            postTextMessage(action.message, action.label);
        }

        function handleMessageKeyDown(event) {
            if (event.key !== "Enter" || !(event.metaKey || event.ctrlKey)) {
                return;
            }

            event.preventDefault();

            if (event.currentTarget.form && typeof event.currentTarget.form.requestSubmit === "function") {
                event.currentTarget.form.requestSubmit();
            }
        }

        async function createTextbookPreview(sourceNote) {
            if (!chatData || previewingTextbook || savingTextbook) {
                return;
            }

            const previewSourceNote = typeof sourceNote === "string" ? sourceNote : "";

            setPreviewingTextbook(true);
            setError("");
            setTextbookPreview(null);

            try {
                const data = await api(`/api/chat/${chatData.thread.id}/textbook_preview`, {
                    method: "POST",
                    body: JSON.stringify({ source_note: previewSourceNote })
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
                        introduction: textbookPreview.introduction || "",
                        learning_image: textbookPreview.learning_image || "",
                        beginner_explanation: textbookPreview.beginner_explanation || "",
                        visual_diagram: textbookPreview.visual_diagram || "",
                        code_example: textbookPreview.code_example || "",
                        code_walkthrough: textbookPreview.code_walkthrough || "",
                        personal_points: textbookPreview.personal_points || "",
                        basic_explanation: textbookPreview.basic_explanation || "",
                        concrete_examples: textbookPreview.concrete_examples || "",
                        key_points: textbookPreview.key_points || "",
                        weak_points: textbookPreview.weak_points || "",
                        unclear_points: textbookPreview.unclear_points || "",
                        common_mistakes: textbookPreview.common_mistakes || "",
                        check_questions: textbookPreview.check_questions || "",
                        application_questions: textbookPreview.application_questions || "",
                        listening_questions: textbookPreview.listening_questions || "",
                        pronunciation_questions: textbookPreview.pronunciation_questions || "",
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

            let deleteRoadmap = false;

            if (chatData.thread.has_roadmap) {
                deleteRoadmap = window.confirm(
                    `この会話には${chatData.thread.title}のロードマップが紐づいています。\n\nOK: 会話とロードマップを削除\nキャンセル: 次に会話だけ削除するか確認`
                );

                if (!deleteRoadmap) {
                    const deleteOnlyThread = window.confirm(
                        `${chatData.thread.title}の会話だけ削除しますか？\n\nロードマップ・教科書・理解度・Memoryは残ります。`
                    );

                    if (!deleteOnlyThread) {
                        return;
                    }
                }
            } else if (!window.confirm(`${chatData.thread.title}を削除しますか？`)) {
                return;
            }

            await api(
                `/api/chat_threads/${chatData.thread.id}${deleteRoadmap ? "?delete_roadmap=true" : ""}`,
                { method: "DELETE" }
            );
            navigate("/", { direction: "back", message: "ホームへ戻っています" });
        }

        const thread = chatData ? chatData.thread : null;
        const messages = chatData ? chatData.messages : [];
        const context = thread && thread.study_context ? thread.study_context : {};
        const lessonActions = [
            {
                label: "ロードマップ通り",
                message: "ロードマップ通りに進もう。現在地から授業を始めてください。"
            },
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
            },
            {
                label: "苦手を整理",
                message: "今までの会話から、僕がつまずいているところを短く整理して、次に何を復習すべきか教えてください。"
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
                    ),
                    h(
                        "div",
                        { className: "study-insight-grid" },
                        h(
                            "article",
                            null,
                            h("span", null, "現在地"),
                            h("strong", null, context.roadmap_current || context.roadmap_status_line || "未設定")
                        ),
                        h(
                            "article",
                            null,
                            h("span", null, "次の一歩"),
                            h("strong", null, context.roadmap_next || context.next_suggestion || "一緒に決める")
                        ),
                        h(
                            "article",
                            null,
                            h("span", null, "教科書"),
                            h("strong", null, context.latest_textbook_title || "まだありません")
                        ),
                        h(
                            "article",
                            null,
                            h("span", null, "苦手メモ"),
                            h("strong", null, context.weak_note || "まだ少ない")
                        ),
                        context.due_review_count
                            ? h(
                                "article",
                                null,
                                h("span", null, "復習候補"),
                                h("strong", null, (context.due_review_items || []).join(" / ") || `${context.due_review_count}件`)
                            )
                            : null
                    )
                    ,
                    context.should_suggest_textbook
                        ? h(
                            "section",
                            { className: "study-next-proposal" },
                            h("div", null,
                                h("span", null, "教科書候補"),
                                h("strong", null, "今日の授業を教科書に追加できます。"),
                                h("p", null, context.textbook_proposal || "授業のまとめを教材として残せます。")
                            ),
                            h(
                                "button",
                                {
                                    type: "button",
                                    onClick: function () {
                                        createTextbookPreview(context.textbook_proposal || "今日の授業終了まとめから教科書に追加してください。");
                                    },
                                    disabled: previewingTextbook || savingTextbook || !chatData
                                },
                                previewingTextbook ? h(LoadingLabel, { text: "準備中" }) : "プレビューを見る"
                            )
                        )
                        : null
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
                            const isStreamingPlaceholder = chat.temp_id && !chat.content;
                            const messageText = chat.content || (isStreamingPlaceholder ? "先生が考えています" : "");
                            const audioContext = chatData && chatData.thread ? chatData.thread.title : "";
                            const hasLanguageAudioTarget = hasConversationLanguageAudioText(messageText, audioContext);
                            return h(
                                "div",
                                {
                                    key: index,
                                    className: `study-message ${chat.role === "user" ? "student-message" : "teacher-message"}${isStreamingPlaceholder ? " thinking-message" : ""}`
                                },
                                h("p", null, messageText),
                                hasLanguageAudioTarget && !isStreamingPlaceholder
                                    ? h(LanguageAudioTools, {
                                        text: messageText,
                                        contextLabel: audioContext,
                                        label: "聞く",
                                        sourceType: "chat"
                                    })
                                    : null
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
                        [
                            "introduction",
                            "learning_image",
                            "beginner_explanation",
                            "visual_diagram",
                            "code_example",
                            "code_walkthrough",
                            "key_points",
                            "personal_points",
                            "check_questions",
                            "application_questions",
                            "listening_questions",
                            "pronunciation_questions"
                        ].map(function (field) {
                            const labels = {
                                introduction: "導入",
                                learning_image: "イメージ",
                                beginner_explanation: "基本説明",
                                visual_diagram: "図・流れ",
                                code_example: "実際のコード・実例",
                                code_walkthrough: "コード解説",
                                key_points: "ここだけは覚えよう",
                                personal_points: "あなた専用ポイント",
                                check_questions: "理解確認問題",
                                application_questions: "応用問題",
                                listening_questions: "リスニング用問題",
                                pronunciation_questions: "発音問題"
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
                            onClick: function () {
                                createTextbookPreview("");
                            },
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
                    h("textarea", {
                        name: "message",
                        placeholder: file ? "画像について聞きたいこと" : "分からないところを聞く",
                        autoComplete: "off",
                        rows: 1,
                        value: message,
                        onKeyDown: handleMessageKeyDown,
                        onChange: function (event) {
                            setMessage(event.target.value);
                        },
                        disabled: sending || !chatData
                    }),
                    sending
                        ? h(
                            "button",
                            {
                                type: "button",
                                className: "stop-button",
                                onClick: stopGenerating
                            },
                            sendingLabel === "停止しています" ? h(LoadingLabel, { text: "停止中" }) : "停止"
                        )
                        : h(
                            "button",
                            { type: "submit", disabled: !chatData || (!message.trim() && !file) },
                            "送信"
                        )
                )
            )
        );
    }

    ReactDOM.createRoot(document.getElementById("pas-react-root")).render(h(App));
})();
