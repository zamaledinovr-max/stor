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
