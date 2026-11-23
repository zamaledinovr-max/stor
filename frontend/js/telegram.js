/**
 * Thin Telegram WebApp wrapper.
 *
 * `initData` is the only source of identity: it is sent in an Authorization
 * header and validated on the server with the official HMAC algorithm.
 */

const webApp = window.Telegram?.WebApp ?? null;

export function initTelegram() {
  if (!webApp) return false;
  try {
    webApp.ready();
    webApp.expand();
    webApp.setHeaderColor?.("secondary_bg_color");
    webApp.disableVerticalSwipes?.();
  } catch (error) {
    console.warn("Telegram WebApp initialisation failed", error);
  }
  return true;
}

/** Raw initData or an empty string outside Telegram. */
export function getInitData() {
  if (webApp?.initData) return webApp.initData;
  try {
    return window.localStorage.getItem("dev_init_data") || "";
  } catch {
    return "";
  }
}

/**
 * Wait until Telegram injects `initData`.
 *
 * On a cold start the WebApp script may finish after our modules run, so the
 * first paint sees an empty string. Poll for a short while and wake up on
 * focus/visibility changes; resolves with the raw string or "" on timeout.
 */
export function waitForInitData(timeoutMs = 3000, intervalMs = 150) {
  return new Promise((resolve) => {
    const startedAt = Date.now();
    let settled = false;
    let timer = null;

    const onWake = () => {
      const value = getInitData();
      if (value) finish(value);
    };

    const stop = () => {
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onWake);
      window.removeEventListener("focus", onWake);
    };

    const finish = (value) => {
      if (settled) return;
      settled = true;
      stop();
      resolve(value);
    };

    const poll = () => {
      const value = getInitData();
      if (value) {
        finish(value);
        return;
      }
      if (Date.now() - startedAt >= timeoutMs) {
        finish("");
        return;
      }
      timer = window.setTimeout(poll, intervalMs);
    };

    document.addEventListener("visibilitychange", onWake);
    window.addEventListener("focus", onWake);
    poll();
  });
}

/** start_param from a t.me/...?startapp= link or an explicit ?listing= URL. */
export function getStartParam() {
  const fromTelegram = webApp?.initDataUnsafe?.start_param;
  if (fromTelegram) return String(fromTelegram);
  const params = new URLSearchParams(window.location.search);
  return params.get("startapp") || "";
}

export function getListingIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const value = params.get("listing");
  const parsed = Number.parseInt(value || "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export function openLink(url) {
  if (!url) return;
  try {
    if (webApp?.openLink) {
      webApp.openLink(url);
      return;
    }
  } catch (error) {
    console.warn("openLink failed", error);
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

/** Open the native Telegram "share to chat" dialog. */
export function shareToTelegram(url, text) {
  const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`;
  try {
    if (webApp?.openTelegramLink) {
      webApp.openTelegramLink(shareUrl);
      return;
    }
  } catch (error) {
    console.warn("share failed", error);
  }
  window.open(shareUrl, "_blank", "noopener,noreferrer");
}

export function haptic(type = "light") {
  try {
    webApp?.HapticFeedback?.impactOccurred(type);
  } catch {
    /* haptics are optional */
  }
}

export function getTelegramUser() {
  return webApp?.initDataUnsafe?.user ?? null;
}

export function isInsideTelegram() {
  return Boolean(webApp?.initData);
}
