/** Listing detail bottom sheet. */

import { clear, el, show } from "../dom.js";
import { formatDateTime, formatListingPrice, timeAgo } from "../format.js";
import { openLink } from "../telegram.js";

export function createDetailView({ api, openSupport, notify, onChanged }) {
  const sheet = document.getElementById("detail-sheet");
  const body = document.getElementById("detail-body");
  const closeButton = document.getElementById("detail-close");
  let currentId = null;
  let current = null;

  function close() {
    show(sheet, false);
    clear(body);
    currentId = null;
    current = null;
  }

  function renderGallery(listing) {
    if (!listing.photos?.length) {
      return el("div", {
        class: "detail__placeholder",
        text: "Продавец не добавил фотографии",
      });
    }
    const gallery = el("div", { class: "detail__gallery" });
    for (const photo of listing.photos) {
      const image = el("img", {
        src: photo.url,
        alt: listing.title,
        loading: "lazy",
        decoding: "async",
      });
      gallery.appendChild(el("div", { class: "detail__photo" }, [image]));
    }
    return gallery;
  }

  async function changeStatus(status, button) {
    if (!current) return;
    button.disabled = true;
    try {
      current = await api.updateStatus(current.id, status);
      notify("Статус обновлён.");
      render();
      onChanged?.();
    } catch (error) {
      notify(error.message || "Не удалось изменить статус.", true);
      button.disabled = false;
    }
  }

  function renderActions(listing) {
    const actions = el("div", { class: "detail__actions" });

    if (listing.is_owner && listing.available_statuses.length) {
      const row = el("div", { class: "detail__actions-row" });
      for (const option of listing.available_statuses) {
        if (option.value === listing.status) continue;
        const label =
          option.value === "active"
            ? "Вернуть в продажу"
            : option.value === "sold"
              ? "Отметить проданным"
              : "Закрыть объявление";
        row.appendChild(
          el("button", {
            class:
              option.value === "active" ? "button button--ghost" : "button button--primary",
            type: "button",
            text: label,
            onclick: (event) => changeStatus(option.value, event.currentTarget),
          }),
        );
      }
      if (row.childElementCount) actions.appendChild(row);
    }

    if (!listing.is_owner) {
      if (listing.owner_username) {
        actions.appendChild(
          el("button", {
            class: "button button--primary",
            type: "button",
            text: "Написать продавцу",
            onclick: () => openLink(`https://t.me/${listing.owner_username}`),
          }),
        );
      } else {
        actions.appendChild(
          el("button", {
            class: "button button--ghost",
            type: "button",
            text: "Связаться через поддержку",
            onclick: openSupport,
          }),
        );
        actions.appendChild(
          el("p", {
            class: "detail__meta",
            text: "Продавец не указал публичный username — напишите в поддержку каталога.",
          }),
        );
      }
    }

    actions.appendChild(
      el("p", {
        class: "detail__meta",
        text: `Опубликовано ${timeAgo(listing.created_at)} · ${formatDateTime(listing.created_at)}`,
      }),
    );
    return actions;
  }

  function render() {
    const listing = current;
    clear(body);

    body.appendChild(renderGallery(listing));

    const head = el("div", { class: "detail__head" }, [
      el("div", { class: "detail__price", text: formatListingPrice(listing) }),
      el("span", { class: "detail__badge", text: listing.kind_label }),
    ]);
    body.appendChild(head);
    body.appendChild(el("h2", { class: "detail__title", text: listing.title }));

    const badges = el("div", { class: "detail__badges" }, [
      el("span", { class: "detail__badge", text: listing.status_label }),
      el("span", { class: "detail__badge", text: listing.district }),
    ]);
    if (listing.condition_label) {
      badges.appendChild(el("span", { class: "detail__badge", text: listing.condition_label }));
    }
    body.appendChild(badges);

    body.appendChild(
      el("dl", { class: "detail__info" }, [
        el("div", { class: "detail__row" }, [
          el("dt", { text: "Тип" }),
          el("dd", { text: listing.kind_label }),
        ]),
        el("div", { class: "detail__row" }, [
          el("dt", { text: listing.kind === "buy" ? "Бюджет" : "Цена" }),
          el("dd", { text: formatListingPrice(listing) }),
        ]),
        el("div", { class: "detail__row" }, [
          el("dt", { text: "Состояние" }),
          el("dd", { text: listing.condition_label || "Не указано" }),
        ]),
        el("div", { class: "detail__row" }, [
          el("dt", { text: "Район" }),
          el("dd", { text: listing.district }),
        ]),
        el("div", { class: "detail__row" }, [
          el("dt", { text: "Продавец" }),
          el("dd", { text: listing.owner_display_name }),
        ]),
      ]),
    );

    if (listing.description) {
      body.appendChild(el("h3", { class: "detail__section-title", text: "Описание" }));
      body.appendChild(el("p", { class: "detail__description", text: listing.description }));
    }

    body.appendChild(renderActions(listing));
  }

  function renderState(message, isError) {
    clear(body);
    body.appendChild(
      el("div", { class: "state" }, [
        el("div", { class: "state__icon", text: isError ? "⚠️" : "⏳" }),
        el("div", {
          class: "state__title",
          text: isError ? "Не удалось открыть объявление" : "Загрузка…",
        }),
        el("div", { class: "state__text", text: message }),
      ]),
    );
  }

  async function load(id) {
    try {
      const listing = await api.getListing(id);
      if (currentId !== id) return;
      current = listing;
      render();
    } catch (error) {
      if (currentId !== id) return;
      renderState(error.message || "Проверьте соединение.", true);
    }
  }

  function open(id) {
    currentId = id;
    current = null;
    renderState("Загружаем объявление…", false);
    show(sheet, true);
    load(id);
  }

  function mount() {
    closeButton.addEventListener("click", close);
    sheet.addEventListener("click", (event) => {
      if (event.target === sheet) close();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !sheet.hidden) close();
    });
  }

  return { mount, open, close, reload: () => current && load(current.id) };
}
