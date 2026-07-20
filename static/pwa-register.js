(() => {
    let deferredInstallPrompt = null;

    const isStandalone = () => (
        window.matchMedia("(display-mode: standalone)").matches
        || window.navigator.standalone === true
    );

    const updateInstallUI = () => {
        const button = document.querySelector("[data-pwa-install]");
        const help = document.querySelector("[data-pwa-install-help]");
        if (!button || !help) return;

        if (isStandalone()) {
            button.hidden = true;
            help.textContent = "この端末にはStudy PASがインストールされています。";
            return;
        }

        if (deferredInstallPrompt) {
            button.hidden = false;
            help.textContent = "ホーム画面から、通常のアプリと同じように起動できます。";
            return;
        }

        button.hidden = true;
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
        help.textContent = isIOS
            ? "Safariの共有ボタンから「ホーム画面に追加」を選んでください。"
            : "ブラウザのメニューに「アプリをインストール」または「ホーム画面に追加」が表示されます。";
    };

    window.addEventListener("beforeinstallprompt", (event) => {
        event.preventDefault();
        deferredInstallPrompt = event;
        updateInstallUI();
    });

    window.addEventListener("appinstalled", () => {
        deferredInstallPrompt = null;
        updateInstallUI();
    });

    document.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-pwa-install]");
        if (!button || !deferredInstallPrompt) return;
        await deferredInstallPrompt.prompt();
        deferredInstallPrompt = null;
        updateInstallUI();
    });

    window.addEventListener("DOMContentLoaded", updateInstallUI);

    if (!("serviceWorker" in navigator)) {
        window.addEventListener("DOMContentLoaded", () => {
            const help = document.querySelector("[data-pwa-install-help]");
            if (help) help.textContent = "このブラウザはアプリのインストールに対応していません。";
        });
        return;
    }

    window.addEventListener("load", () => {
        navigator.serviceWorker.register("/service-worker.js", { scope: "/" })
            .catch((error) => console.warn("Service Worker registration failed", error));
    });
})();
