/** Application shell: bootstrap, tabs, support and global error handling. */

import { ApiClient } from "./api.js";
import { el } from "./dom.js";
import {
  getInitData,
  getListingIdFromUrl,
  getStartParam,
  haptic,
  initTelegram,
  openLink,
} from "./telegram.js";
import { createAccountView } from "./views/account.js";
import { createCatalogView } from "./views/catalog.js";
import { createCreateView } from "./views/create.js";
import { createDetailView } from "./views/detail.js";

const api = new ApiClient();
const state = { meta: null, me: null };
const toastNode = document.getElementById("toast");

let catalog = null;
let account = null;
let createView = null;
let detail = null;
let toastTimer = null;

function notify(message, isError = false) {
  if (!toastNode) return;
  toastNode.textContent = message;
  toastNode.classList.toggle("toast--error", Boolean(isError));
  toastNode.hidden = false;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(
    () => {
      toastNode.hidden = true;
    },
    isError ? 5000 : 2600,
  );
  haptic(isError ? "rigid" : "light");
}

function openSupport() {
  const support = state.meta?.support;
  if (!support?.url) {
    notify("Поддержка пока не настроена. Напишите администратору канала.", true);
    return;
  }
  openLink(support.url);
}

function parseStartParam(value) {
  if (!value) return null;
  const match = /^(?:listing_?)?(\d{1,10})$/.exec(String(value).trim());
  if (!match) return null;
  const id = Number.parseInt(match[1], 10);
  return Number.isFinite(id) && id > 0 ? id : null;
}

function refreshOwnData() {
  if (account && !document.getElementById("view-account").hidden) account.refresh();
  if (catalog && !document.getElementById("view-catalog").hidden) catalog.refresh();
}

function switchTab(tab) {
  const views = {
    catalog: document.getElementById("view-catalog"),
    sell: document.getElementById("view-sell"),
    account: document.getElementById("view-account"),
  };
  if (!views[tab]) return;
  for (const [name, node] of Object.entries(views)) node.hidden = name !== tab;
  for (const button of document.querySelectorAll(".tabbar__item")) {
    const active = button.dataset.tab === tab;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  }
  if (tab === "account" && account) account.refresh();
  if (tab === "catalog" && catalog && !catalog.state.loaded) catalog.refresh();
  haptic("light");
}

function goCatalog() {
  switchTab("catalog");
  if (catalog) catalog.refresh();
  if (account) account.refresh();
}

function goAccount() {
  switchTab("account");
  if (account) account.refresh();
}

async function openEdit(listingId) {
  if (!createView) return;
  try {
    const listing = await api.getListing(listingId);
    if (detail) detail.close();
    switchTab("sell");
    createView.startEdit(listing);
  } catch (error) {
    notify(error.message || "Не удалось открыть форму редактирования.", true);
  }
}

function buildViews() {
  detail = createDetailView({
    api,
    getMeta: () => state.meta,
    openSupport,
    notify,
    onChanged: refreshOwnData,
    onEdit: openEdit,
  });
  catalog = createCatalogView({
    api,
    getMeta: () => state.meta,
    openListing: (id) => detail.open(id),
    openLink,
    notify,
  });
  account = createAccountView({
    api,
    getMe: () => state.me,
    openListing: (id) => detail.open(id),
    openCreate: () => switchTab("sell"),
    openEdit,
    notify,
  });
  createView = createCreateView({
    api,
    getMeta: () => state.meta,
    openListing: (id) => detail.open(id),
    goCatalog,
    goAccount,
    onCancel: () => {
      createView.reset();
      goAccount();
    },
    notify,
  });

  catalog.mount();
  account.mount();
  createView.mount();
  detail.mount();

  document.getElementById("app-name").textContent = state.meta.app_name;
  document.title = state.meta.app_name;
  account.renderProfile();
  catalog.refresh();
  account.refresh();
}

function showFatal(error) {
  const tabbar = document.querySelector(".tabbar");
  if (tabbar) tabbar.hidden = true;
  const isAuth = !getInitData() || error?.status === 401;
  const message = isAuth
    ? "Откройте приложение кнопкой «Открыть каталог» в Telegram-боте: данные входа передаются только внутри Telegram."
    : error?.message || "Проверьте соединение и попробуйте ещё раз.";
  const main = document.querySelector(".main");
  main.replaceChildren(
    el("div", { class: "state" }, [
      el("div", { class: "state__icon", text: "🔒" }),
      el("div", { class: "state__title", text: "Не удалось открыть каталог" }),
      el("div", { class: "state__text", text: message }),
      el("button", {
        class: "button button--primary",
        type: "button",
        text: "Повторить",
        onclick: () => window.location.reload(),
      }),
    ]),
  );
}

function bindShell() {
  for (const button of document.querySelectorAll(".tabbar__item")) {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
  }
  for (const id of ["support-button", "support-button-2"]) {
    document.getElementById(id)?.addEventListener("click", openSupport);
  }
}

async function boot() {
  initTelegram();
  bindShell();

  if (!getInitData()) {
    showFatal(null);
    return;
  }

  try {
    const [meta, me] = await Promise.all([api.getMeta(), api.getMe()]);
    state.meta = meta;
    state.me = me;
  } catch (error) {
    console.error("Bootstrap failed", error);
    showFatal(error);
    return;
  }

  buildViews();

  const listingId = getListingIdFromUrl() || parseStartParam(getStartParam());
  if (listingId) detail.open(listingId);
}

boot();
