/** Listing detail bottom sheet. */

import { clear, el, show } from "../dom.js";
import { formatDateTime, formatListingPrice, timeAgo } from "../format.js";
import { openLink } from "../telegram.js";

export function createDetailView({ api, getMeta, openSupport, notify, onChanged, onEdit }) {
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

  function renderComplaintWidget(listing) {
    const reasons = getMeta()?.complaint_reasons || [];
    if (!reasons.length) return null;

    const trigger = el("button", {
      class: "button button--ghost",
      type: "button",
      text: "Пожаловаться",
    });
    const form = el("div", { class: "complaint__form", hidden: true });
    const reasonSelect = el(
      "select",
      { class: "input input--select", attrs: { "aria-label": "Причина жалобы" } },
      reasons.map((option) => el("option", { value: option.value, text: option.label })),
    );
    const comment = el("textarea", {
      class: "input input--area",
      rows: 3,
      maxlength: 500,
      placeholder: "Опишите, что не так с объявлением",
      attrs: { "aria-label": "Комментарий к жалобе" },
    });
    const error = el("p", { class: "field__error", hidden: true });
    const submit = el("button", {
      class: "button button--primary",
      type: "button",
      text: "Отправить жалобу",
    });
    const cancel = el("button", {
      class: "button button--ghost",
      type: "button",
      text: "Отмена",
    });

    function closeForm() {
      form.hidden = true;
      show(trigger, true);
      error.hidden = true;
    }

    trigger.addEventListener("click", () => {
      show(trigger, false);
      form.hidden = false;
      reasonSelect.focus();
    });
    cancel.addEventListener("click", closeForm);
    submit.addEventListener("click", async () => {
      const text = comment.value.trim();
      error.hidden = true;
      if (!reasonSelect.value) {
        error.textContent = "Выберите причину жалобы.";
        error.hidden = false;
        return;
      }
      if (text.length < 3) {
        error.textContent = "Опишите проблему — минимум 3 символа.";
        error.hidden = false;
        return;
      }
      submit.disabled = true;
      try {
        await api.createComplaint(listing.id, {
          reason: reasonSelect.value,
          comment: text,
        });
        closeForm();
        comment.value = "";
        notify("Жалоба отправлена. Спасибо!");
      } catch (requestError) {
        error.textContent =
          requestError.message || "Не удалось отправить жалобу. Попробуйте позже.";
        error.hidden = false;
      } finally {
        submit.disabled = false;
      }
    });

    form.appendChild(el("label", { class: "field" }, [
      el("span", { class: "field__label", text: "Причина" }),
      reasonSelect,
    ]));
    form.appendChild(el("label", { class: "field" }, [
      el("span", { class: "field__label", text: "Комментарий" }),
      comment,
    ]));
    form.appendChild(error);
    form.appendChild(el("div", { class: "complaint__actions" }, [submit, cancel]));

    return el("div", { class: "complaint" }, [trigger, form]);
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

    if (listing.is_owner) {
      actions.appendChild(
        el("button", {
          class: "button button--ghost",
          type: "button",
          text: "Редактировать объявление",
          onclick: () => onEdit?.(listing.id),
        }),
      );
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

    if (!listing.is_owner) {
      const complaintWidget = renderComplaintWidget(listing);
      if (complaintWidget) actions.appendChild(complaintWidget);
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

    if (listing.moderation_status && listing.moderation_status !== "approved") {
      const notice = el("div", { class: "detail__notice" }, [
        el("strong", { text: listing.moderation_label }),
      ]);
      if (listing.moderation_status === "pending") {
        notice.appendChild(
          el("span", {
            class: "detail__notice-reason",
            text: "Объявление проверяет администратор — в каталоге оно появится после одобрения.",
          }),
        );
      }
      if (listing.moderation_reason) {
        notice.appendChild(
          el("span", {
            class: "detail__notice-reason",
            text: `Причина: ${listing.moderation_reason}`,
          }),
        );
      }
      body.appendChild(notice);
    }

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
