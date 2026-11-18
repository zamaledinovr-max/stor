/** Account view: profile, own listings grouped by status, support entry. */

import { clear, el } from "../dom.js";
import { formatListingPrice, timeAgo } from "../format.js";

const GROUPS = [
  { key: "active", title: "Активные" },
  { key: "sold", title: "Проданные" },
  { key: "closed", title: "Закрытые" },
];

export function createAccountView({ api, getMe, openListing, openCreate, notify }) {
  const profileNode = document.getElementById("account-card");
  const groupsNode = document.getElementById("account-groups");
  let data = null;
  let loading = false;

  function renderProfile() {
    clear(profileNode);
    const me = getMe();
    if (!me) {
      profileNode.appendChild(el("div", { class: "account__meta", text: "Профиль загружается…" }));
      return;
    }
    const user = me.user;
    const initial = (user.first_name || user.username || "?").trim().charAt(0).toUpperCase();
    profileNode.appendChild(el("div", { class: "account__avatar", text: initial }));
    const body = el("div", {}, [
      el("div", { class: "account__name", text: user.display_name }),
      el("div", {
        class: "account__meta",
        text: user.username ? `@${user.username}` : "Telegram-аккаунт",
      }),
    ]);
    if (me.is_admin) {
      body.appendChild(el("div", { class: "account__meta", text: "Администратор" }));
    }
    profileNode.appendChild(body);
  }

  async function changeStatus(item, status, button) {
    button.disabled = true;
    try {
      await api.updateStatus(item.id, status);
      notify("Статус обновлён.");
      await refresh();
    } catch (error) {
      notify(error.message || "Не удалось изменить статус.", true);
      button.disabled = false;
    }
  }

  function statusButton(item) {
    const isActive = item.status === "active";
    const target = isActive ? (item.kind === "sell" ? "sold" : "closed") : "active";
    let label = "Вернуть в продажу";
    if (isActive) label = item.kind === "sell" ? "Отметить проданным" : "Закрыть";
    return el("button", {
      class: "chip",
      type: "button",
      text: label,
      onclick: (event) => changeStatus(item, target, event.currentTarget),
    });
  }

  function accountItem(item) {
    const thumb = item.cover_photo?.url
      ? el("img", {
          class: "account-item__thumb",
          src: item.cover_photo.url,
          alt: "",
          loading: "lazy",
        })
      : el("div", { class: "account-item__thumb account-item__thumb--empty", text: "Нет фото" });

    const body = el("div", { class: "account-item__body" }, [
      el("div", { class: "account-item__title", text: item.title }),
      el("div", { class: "muted", text: `${item.status_label} · ${formatListingPrice(item)}` }),
      el("div", { class: "muted", text: `${item.district} · ${timeAgo(item.created_at)}` }),
      el("div", { class: "account-item__actions" }, [
        el("button", {
          class: "chip",
          type: "button",
          text: "Открыть",
          onclick: () => openListing(item.id),
        }),
        statusButton(item),
      ]),
    ]);

    return el("div", { class: "account-item" }, [thumb, body]);
  }

  function renderEmpty() {
    clear(groupsNode);
    groupsNode.appendChild(
      el("div", { class: "state" }, [
        el("div", { class: "state__icon", text: "📦" }),
        el("div", { class: "state__title", text: "У вас пока нет объявлений" }),
        el("div", {
          class: "state__text",
          text: "Разместите первое объявление — это займёт меньше минуты.",
        }),
        el("button", {
          class: "button button--primary",
          type: "button",
          text: "Разместить объявление",
          onclick: openCreate,
        }),
      ]),
    );
  }

  function renderError(message) {
    clear(groupsNode);
    groupsNode.appendChild(
      el("div", { class: "state" }, [
        el("div", { class: "state__icon", text: "⚠️" }),
        el("div", { class: "state__title", text: "Не удалось загрузить объявления" }),
        el("div", { class: "state__text", text: message }),
        el("button", {
          class: "button button--ghost",
          type: "button",
          text: "Повторить",
          onclick: () => refresh(),
        }),
      ]),
    );
  }

  function renderGroups() {
    clear(groupsNode);
    if (!data) return;
    if (!data.items.length) {
      renderEmpty();
      return;
    }
    for (const group of GROUPS) {
      const items = data.items.filter((item) => item.status === group.key);
      if (!items.length) continue;
      const section = el("section", { class: "account-group" });
      section.appendChild(
        el("h2", { class: "account-group__title" }, [
          group.title,
          el("span", { class: "muted", text: String(items.length) }),
        ]),
      );
      for (const item of items) section.appendChild(accountItem(item));
      groupsNode.appendChild(section);
    }
  }

  function renderLoading() {
    clear(groupsNode);
    groupsNode.appendChild(el("div", { class: "state" }, [
      el("div", { class: "state__text", text: "Загружаем ваши объявления…" }),
    ]));
  }

  async function refresh() {
    if (loading) return;
    loading = true;
    renderProfile();
    if (!data) renderLoading();
    try {
      data = await api.myListings();
      renderGroups();
    } catch (error) {
      data = null;
      renderError(error.message || "Проверьте соединение и попробуйте снова.");
    } finally {
      loading = false;
    }
  }

  return {
    mount: () => {
      renderProfile();
      if (data) renderGroups();
      else renderLoading();
    },
    refresh,
    renderProfile,
    getData: () => data,
  };
}
