/** Account view: profile, own listings grouped by status, support entry. */

import { clear, el } from "../dom.js";
import { formatListingPrice, timeAgo } from "../format.js";

const MODERATION_GROUPS = [
  { key: "pending", title: "На проверке" },
  { key: "rejected", title: "Отклонённые" },
  { key: "removed", title: "Снятые с публикации" },
];

const GROUPS = [
  { key: "active", title: "Активные" },
  { key: "sold", title: "Проданные" },
  { key: "closed", title: "Закрытые" },
];

export function createAccountView({ api, getMe, openListing, openCreate, openEdit, notify }) {
  const profileNode = document.getElementById("account-card");
  const groupsNode = document.getElementById("account-groups");
  const favoritesNode = document.getElementById("account-favorites");
  let data = null;
  let loading = false;
  let favorites = null;
  let favoritesError = null;

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

  function itemThumb(item) {
    return item.cover_photo?.url
      ? el("img", {
          class: "account-item__thumb",
          src: item.cover_photo.url,
          alt: "",
          loading: "lazy",
        })
      : el("div", {
          class: "account-item__thumb account-item__thumb--empty",
          text: "Нет фото",
        });
  }

  function accountItem(item) {
    const thumb = itemThumb(item);

    const approved = item.moderation_status === "approved";
    const stateLabel = approved ? item.status_label : item.moderation_label;
    const actions = [
      el("button", {
        class: "chip",
        type: "button",
        text: "Открыть",
        onclick: () => openListing(item.id),
      }),
      el("button", {
        class: "chip",
        type: "button",
        text: "Редактировать",
        onclick: () => openEdit(item.id),
      }),
    ];
    if (approved) actions.push(statusButton(item));

    const body = el("div", { class: "account-item__body" }, [
      el("div", { class: "account-item__title", text: item.title }),
      el("div", { class: "muted", text: `${stateLabel} · ${formatListingPrice(item)}` }),
      el("div", { class: "muted", text: `${item.district} · ${timeAgo(item.created_at)}` }),
    ]);
    if (!approved && item.moderation_reason) {
      body.appendChild(
        el("div", {
          class: "account-item__reason",
          text: `Причина: ${item.moderation_reason}`,
        }),
      );
    }
    body.appendChild(el("div", { class: "account-item__actions" }, actions));

    return el("div", { class: "account-item" }, [thumb, body]);
  }

  function favoriteItem(item) {
    const stateLabel =
      item.moderation_status === "approved" ? item.status_label : item.moderation_label;
    const body = el("div", { class: "account-item__body" }, [
      el("div", { class: "account-item__title", text: item.title }),
      el("div", { class: "muted", text: `${stateLabel} · ${formatListingPrice(item)}` }),
      el("div", { class: "muted", text: `${item.district} · ${timeAgo(item.created_at)}` }),
      el("div", { class: "account-item__actions" }, [
        el("button", {
          class: "chip",
          type: "button",
          text: "Открыть",
          onclick: () => openListing(item.id),
        }),
        el("button", {
          class: "chip",
          type: "button",
          text: "Убрать",
          onclick: (event) => removeFavorite(item.id, event.currentTarget),
        }),
      ]),
    ]);
    return el("div", { class: "account-item" }, [itemThumb(item), body]);
  }

  async function removeFavorite(id, button) {
    button.disabled = true;
    try {
      await api.removeFavorite(id);
      notify("Убрано из избранного.");
      await refreshFavorites();
    } catch (error) {
      notify(error.message || "Не удалось убрать из избранного.", true);
      button.disabled = false;
    }
  }

  function renderFavorites() {
    if (!favoritesNode) return;
    clear(favoritesNode);
    if (favoritesError) {
      favoritesNode.appendChild(
        el("p", {
          class: "account-group__hint",
          text: "Не удалось загрузить избранное.",
        }),
      );
      return;
    }
    if (favorites === null) return;

    const items = favorites.items || [];
    const section = el("section", { class: "account-group" });
    section.appendChild(
      el("h2", { class: "account-group__title" }, [
        "Избранное",
        el("span", { class: "muted", text: String(items.length) }),
      ]),
    );
    if (!items.length) {
      section.appendChild(
        el("p", {
          class: "account-group__hint",
          text: "Пока пусто. Нажмите ♥ в объявлении, чтобы сохранить его здесь.",
        }),
      );
    } else {
      for (const item of items) section.appendChild(favoriteItem(item));
    }
    favoritesNode.appendChild(section);
  }

  async function refreshFavorites() {
    try {
      favorites = await api.getFavorites();
      favoritesError = null;
    } catch (error) {
      favorites = null;
      favoritesError = error.message || true;
    }
    renderFavorites();
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

  function renderGroup(title, items) {
    if (!items.length) return;
    const section = el("section", { class: "account-group" });
    section.appendChild(
      el("h2", { class: "account-group__title" }, [
        title,
        el("span", { class: "muted", text: String(items.length) }),
      ]),
    );
    for (const item of items) section.appendChild(accountItem(item));
    groupsNode.appendChild(section);
  }

  function renderGroups() {
    clear(groupsNode);
    if (!data) return;
    if (!data.items.length) {
      renderEmpty();
      return;
    }
    for (const group of MODERATION_GROUPS) {
      renderGroup(
        group.title,
        data.items.filter((item) => item.moderation_status === group.key),
      );
    }
    const approved = data.items.filter((item) => item.moderation_status === "approved");
    for (const group of GROUPS) {
      renderGroup(
        group.title,
        approved.filter((item) => item.status === group.key),
      );
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
    refreshFavorites();
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
      renderFavorites();
    },
    refresh,
    renderProfile,
    getData: () => data,
  };
}
