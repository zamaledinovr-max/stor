/** Step-by-step listing creation wizard. */

import { clear, el, setPressed, show } from "../dom.js";
import { formatListingPrice, parsePriceInput } from "../format.js";

const TOTAL_STEPS = 3;

function emptyValues() {
  return {
    title: "",
    description: "",
    condition: "",
    conditionText: "",
    price: "",
    district: "",
  };
}

export function createCreateView({
  api,
  getMeta,
  openListing,
  goCatalog,
  goAccount,
  onCancel,
  notify,
}) {
  const form = document.getElementById("create-form");
  const steps = [...form.querySelectorAll(".wizard-step")];
  const stepbar = document.getElementById("wizard-steps");
  const segmented = document.getElementById("kind-segmented");
  const conditionChips = document.getElementById("condition-chips");
  const conditionTextField = document.getElementById("condition-text-field");
  const conditionTextInput = document.getElementById("field-condition-text");
  const districtInput = document.getElementById("field-district");
  const districtOptions = document.getElementById("district-options");
  const titleInput = document.getElementById("field-title");
  const descriptionInput = document.getElementById("field-description");
  const priceInput = document.getElementById("field-price");
  const noBudgetInput = document.getElementById("field-no-budget");
  const noBudgetRow = document.getElementById("no-budget-row");
  const negotiableInput = document.getElementById("field-price-negotiable");
  const negotiableRow = document.getElementById("price-negotiable-row");
  const photoInput = document.getElementById("photo-input");
  const previews = document.getElementById("photo-previews");
  const summary = document.getElementById("create-summary");
  const limitsNode = document.getElementById("photo-limits");
  const backButton = document.getElementById("wizard-back");
  const nextButton = document.getElementById("wizard-next");
  const submitButton = document.getElementById("wizard-submit");
  const cancelButton = document.getElementById("wizard-cancel");
  const wizardTitle = document.getElementById("wizard-title");
  const titleLabel = document.getElementById("title-label");
  const priceLabel = document.getElementById("price-label");
  const conditionReq = document.getElementById("condition-req");
  const descriptionHint = document.getElementById("description-hint");
  const rulesBlock = document.getElementById("rules-block");
  const rulesText = document.getElementById("rules-text");
  const rulesCheckbox = document.getElementById("field-rules");

  const state = {
    step: 1,
    kind: "sell",
    values: emptyValues(),
    noBudget: false,
    priceNegotiable: false,
    conditionMode: "standard",
    files: [],
    existingPhotos: [],
    removedPhotoIds: [],
    editId: null,
    submitting: false,
  };

  let successNode = null;

  function meta() {
    return getMeta();
  }

  function limits() {
    return meta().photo_limits;
  }

  function clearErrors() {
    for (const node of form.querySelectorAll(".field__error")) {
      node.textContent = "";
      node.hidden = true;
    }
    for (const node of form.querySelectorAll(".input")) node.classList.remove("is-invalid");
  }

  function setError(field, message) {
    const errorNode = document.getElementById(`error-${field}`);
    if (errorNode) {
      errorNode.textContent = message;
      errorNode.hidden = false;
    }
    const input = document.getElementById(`field-${field}`);
    if (input) input.classList.add("is-invalid");
  }

  function validateStep1() {
    const errors = [];
    const title = state.values.title.trim();
    if (title.length < 2) {
      setError("title", "Укажите название — минимум 2 символа.");
      errors.push("title");
    } else if (title.length > 120) {
      setError("title", "Название должно быть короче 120 символов.");
      errors.push("title");
    }
    if (state.values.description.length > 1000) {
      setError("description", "Описание должно быть короче 1000 символов.");
      errors.push("description");
    }
    return errors;
  }

  function validateStep2() {
    const errors = [];
    const customCondition = state.conditionMode === "custom";
    const conditionText = state.values.conditionText.trim();

    if (customCondition) {
      if (!conditionText) {
        setError("condition", "Введите своё состояние.");
        errors.push("condition");
      } else if (conditionText.length > 40) {
        setError("condition", "Состояние должно быть короче 40 символов.");
        errors.push("condition");
      }
    } else if (state.kind === "sell" && !state.values.condition) {
      setError("condition", "Выберите состояние устройства.");
      errors.push("condition");
    }

    if (state.kind === "sell") {
      if (!state.priceNegotiable) {
        if (!state.values.price.trim()) {
          setError("price", "Укажите цену или выберите «Договорная».");
          errors.push("price");
        } else if (!parsePriceInput(state.values.price)) {
          setError("price", "Цена должна быть положительным числом.");
          errors.push("price");
        }
      }
    } else if (!state.noBudget && !state.values.price.trim()) {
      setError("price", "Укажите бюджет или отметьте «Бюджет не указан».");
      errors.push("price");
    } else if (!state.noBudget && state.values.price.trim()) {
      if (!parsePriceInput(state.values.price)) {
        setError("price", "Бюджет должен быть положительным числом.");
        errors.push("price");
      }
    }
    const district = state.values.district.trim();
    if (!district) {
      setError("district", "Укажите место встречи.");
      errors.push("district");
    } else if (district.length < 2) {
      setError("district", "Место встречи слишком короткое.");
      errors.push("district");
    } else if (district.length > 40) {
      setError("district", "Место встречи должно быть короче 40 символов.");
      errors.push("district");
    }
    return errors;
  }

  function validateStep3() {
    const { max_count: maxCount, max_size_mb: maxSize, allowed_mime_types: allowed } = limits();
    const errors = [];
    if (state.files.length + state.existingPhotos.length > maxCount) {
      setError("photos", `Можно добавить не больше ${maxCount} фотографий.`);
      errors.push("photos");
    }
    for (const item of state.files) {
      if (!allowed.includes(item.file.type)) {
        setError("photos", "Недопустимый формат файла. Разрешены JPEG, PNG и WEBP.");
        errors.push("photos");
        break;
      }
      if (item.file.size > maxSize * 1024 * 1024) {
        setError("photos", `Каждый файл должен быть не больше ${maxSize} МБ.`);
        errors.push("photos");
        break;
      }
    }
    if (meta().rules && !state.editId && !rulesCheckbox.checked) {
      setError("rules", "Подтвердите, что объявление соответствует правилам.");
      errors.push("rules");
    }
    return errors;
  }

  function validateStep(step) {
    const errors = step === 1 ? validateStep1() : step === 2 ? validateStep2() : validateStep3();
    if (errors.length) {
      notify("Проверьте выделенные поля.", true);
      document
        .getElementById(`error-${errors[0]}`)
        ?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    return errors.length === 0;
  }

  function renderKind() {
    clear(segmented);
    for (const option of meta().kinds) {
      const button = el("button", {
        class: "segmented__item",
        type: "button",
        text: option.label,
        onclick: () => {
          if (state.kind === option.value) return;
          state.kind = option.value;
          if (state.kind === "buy") {
            state.values.condition = "";
            state.values.conditionText = "";
            state.conditionMode = "standard";
            conditionTextInput.value = "";
            state.priceNegotiable = false;
            negotiableInput.checked = false;
          } else {
            state.noBudget = false;
            noBudgetInput.checked = false;
          }
          renderKind();
          renderConditionChips();
          syncKindLabels();
          updatePhotoSummary();
        },
      });
      setPressed(button, state.kind === option.value);
      if (state.editId) {
        button.disabled = true;
        button.title = "Тип объявления нельзя изменить";
      }
      segmented.appendChild(button);
    }
  }

  function syncKindLabels() {
    const isSell = state.kind === "sell";
    titleLabel.textContent = isSell ? "Название устройства" : "Что ищете?";
    const required = el("span", { class: "req", text: "*" });
    titleLabel.appendChild(required);
    titleInput.placeholder = isSell
      ? "Например, Pasito 3 в хорошем состоянии"
      : "Например, Xros 6 mini, бюджет 1600";
    descriptionInput.placeholder = isSell
      ? "Например: покупал в марте, есть чек и две капсулы…"
      : "Например: нужен Xros 6 mini, цвет чёрный, до 1600 ₽";
    descriptionHint.textContent = isSell
      ? "Состояние, что в комплекте, причина продажи."
      : "Модель, цвет, бюджет, сроки.";
    priceLabel.textContent = isSell ? "Цена, ₽" : "Максимальный бюджет, ₽";
    if (isSell && !state.priceNegotiable) {
      priceLabel.appendChild(el("span", { class: "req", text: "*" }));
    }
    show(noBudgetRow, !isSell);
    show(negotiableRow, isSell);
    show(conditionTextField, state.conditionMode === "custom");
    conditionReq.hidden = !isSell;
    priceInput.disabled = (isSell && state.priceNegotiable) || (!isSell && state.noBudget);
    if (state.noBudget || (isSell && state.priceNegotiable)) priceInput.value = "";
  }

  function renderConditionChips() {
    clear(conditionChips);
    for (const option of meta().conditions) {
      const active =
        state.conditionMode === "standard" && state.values.condition === option.value;
      const button = el("button", {
        class: "chip",
        type: "button",
        text: option.label,
        onclick: () => {
          state.conditionMode = "standard";
          state.values.condition =
            state.values.condition === option.value ? "" : option.value;
          state.values.conditionText = "";
          conditionTextInput.value = "";
          renderConditionChips();
          syncKindLabels();
        },
      });
      setPressed(button, active);
      conditionChips.appendChild(button);
    }

    const customButton = el("button", {
      class: "chip",
      type: "button",
      text: "Своё состояние",
      onclick: () => {
        state.conditionMode = "custom";
        state.values.condition = "";
        renderConditionChips();
        syncKindLabels();
        conditionTextInput.focus();
      },
    });
    setPressed(customButton, state.conditionMode === "custom");
    conditionChips.appendChild(customButton);
  }

  function renderDistricts() {
    clear(districtOptions);
    for (const district of meta().districts) {
      districtOptions.appendChild(el("option", { value: district }));
    }
    districtInput.value = state.values.district;
  }

  function renderRules() {
    if (state.editId) {
      show(rulesBlock, false);
      rulesCheckbox.checked = false;
      return;
    }
    const rules = meta().rules;
    if (!rules) {
      show(rulesBlock, false);
      rulesCheckbox.checked = false;
      return;
    }
    rulesText.textContent = rules;
    show(rulesBlock, true);
  }

  function renderPhotos() {
    clear(previews);
    for (const photo of state.existingPhotos) {
      const image = el("img", { src: photo.url, alt: "Фото объявления" });
      const remove = el("button", {
        class: "photo-thumb__remove",
        type: "button",
        text: "×",
        attrs: { "aria-label": "Удалить фотографию" },
        onclick: () => removeExistingPhoto(photo.id),
      });
      previews.appendChild(el("div", { class: "photo-thumb" }, [image, remove]));
    }
    for (const [index, item] of state.files.entries()) {
      const image = el("img", { src: item.url, alt: `Фото ${index + 1}` });
      const remove = el("button", {
        class: "photo-thumb__remove",
        type: "button",
        text: "×",
        attrs: { "aria-label": "Удалить фотографию" },
        onclick: () => removeFile(index),
      });
      previews.appendChild(el("div", { class: "photo-thumb" }, [image, remove]));
    }
  }

  function removeExistingPhoto(photoId) {
    state.existingPhotos = state.existingPhotos.filter((item) => item.id !== photoId);
    if (!state.removedPhotoIds.includes(photoId)) {
      state.removedPhotoIds.push(photoId);
    }
    renderPhotos();
    updatePhotoSummary();
  }

  function removeFile(index) {
    const [item] = state.files.splice(index, 1);
    if (item) URL.revokeObjectURL(item.url);
    renderPhotos();
    updatePhotoSummary();
  }

  function addFiles(fileList) {
    clearErrors();
    const { max_count: maxCount, max_size_mb: maxSize, allowed_mime_types: allowed } = limits();
    const nextFiles = [...state.files];
    for (const file of fileList) {
      if (nextFiles.length + state.existingPhotos.length >= maxCount) {
        notify(`Можно добавить не больше ${maxCount} фотографий.`, true);
        break;
      }
      if (!allowed.includes(file.type)) {
        notify(`Файл «${file.name}» пропущен: допустимы JPEG, PNG и WEBP.`, true);
        continue;
      }
      if (file.size > maxSize * 1024 * 1024) {
        notify(`Файл «${file.name}» пропущен: больше ${maxSize} МБ.`, true);
        continue;
      }
      nextFiles.push({ file, url: URL.createObjectURL(file) });
    }
    state.files = nextFiles;
    photoInput.value = "";
    renderPhotos();
    updatePhotoSummary();
  }

  function updatePhotoSummary() {
    if (state.step === TOTAL_STEPS) renderSummary();
  }

  function renderSummary() {
    clear(summary);
    const conditionLabel =
      state.conditionMode === "custom"
        ? state.values.conditionText.trim() || "Не указано"
        : meta().conditions.find((item) => item.value === state.values.condition)?.label ||
          "Не указано";
    const parsedPrice = parsePriceInput(state.values.price);
    const priceValue =
      state.kind === "buy" && state.noBudget
        ? "Не указан"
        : formatListingPrice({
            kind: state.kind,
            price_negotiable: state.kind === "sell" && state.priceNegotiable,
            price: parsedPrice ? { amount: parsedPrice, currency: "RUB" } : null,
          });

    const rows = [
      ["Тип", meta().kinds.find((item) => item.value === state.kind)?.label || ""],
      ["Название", state.values.title.trim() || "—"],
      ["Состояние", conditionLabel],
      [state.kind === "buy" ? "Бюджет" : "Цена", priceValue],
      ["Место встречи", state.values.district || "—"],
      ["Фотографии", String(state.files.length + state.existingPhotos.length)],
    ];
    for (const [label, value] of rows) {
      summary.appendChild(
        el("div", { class: "summary__row" }, [
          el("dt", { text: label }),
          el("dd", { text: value }),
        ]),
      );
    }
    const limitsInfo = limits();
    limitsNode.textContent = `До ${limitsInfo.max_count} фото, ${limitsInfo.max_size_mb} МБ каждое. Разрешены JPEG, PNG, WEBP.`;
  }

  function renderStepbar() {
    clear(stepbar);
    for (let index = 1; index <= TOTAL_STEPS; index += 1) {
      const node = el("div", { class: "stepbar__item" });
      if (index <= state.step) node.classList.add("is-done");
      stepbar.appendChild(node);
    }
  }

  function showStep(step) {
    state.step = step;
    steps.forEach((node) => {
      node.hidden = Number(node.dataset.step) !== step;
    });
    show(backButton, step > 1);
    show(nextButton, step < TOTAL_STEPS);
    show(submitButton, step === TOTAL_STEPS);
    show(cancelButton, Boolean(state.editId));
    renderStepbar();
    if (step === TOTAL_STEPS) renderSummary();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function setSubmitLabel(text) {
    submitButton.textContent = text;
  }

  async function uploadPhotos(listingId) {
    const failures = [];
    for (const [index, item] of state.files.entries()) {
      setSubmitLabel(`Загрузка фото ${index + 1}/${state.files.length}…`);
      try {
        await api.uploadPhoto(listingId, item.file);
      } catch (error) {
        failures.push(error.message || "не удалось загрузить фото");
      }
    }
    return failures;
  }

  function buildFieldsPayload() {
    const price = state.priceNegotiable
      ? null
      : state.kind === "buy" && state.noBudget
        ? null
        : parsePriceInput(state.values.price);
    return {
      title: state.values.title.trim(),
      description: state.values.description.trim() || null,
      condition: state.conditionMode === "standard" ? state.values.condition || null : null,
      condition_text:
        state.conditionMode === "custom"
          ? state.values.conditionText.trim() || null
          : null,
      price_amount: price,
      price_negotiable: state.kind === "sell" && state.priceNegotiable,
      district: state.values.district,
    };
  }

  function buildPayload() {
    return {
      kind: state.kind,
      ...buildFieldsPayload(),
      rules_accepted: rulesCheckbox.checked,
    };
  }

  function applyServerErrors(error) {
    const fieldMap = {
      title: "title",
      description: "description",
      condition: "condition",
      condition_text: "condition",
      price_amount: "price",
      price_negotiable: "price",
      district: "district",
      kind: "title",
      rules_accepted: "rules",
    };
    const firstField = error.fields?.[0]?.field?.split(".").pop();
    if (firstField && fieldMap[firstField]) {
      setError(fieldMap[firstField], error.fields[0].message);
      if (["title", "kind", "description"].includes(firstField)) showStep(1);
      else if (firstField === "rules_accepted") showStep(3);
      else showStep(2);
      return;
    }
    if (error.message) notify(error.message, true);
  }

  function renderSuccess(listing, photoFailures, isEdit = false) {
    form.hidden = true;
    if (successNode) successNode.remove();

    const pending = listing.moderation_status === "pending";
    const title = isEdit
      ? pending
        ? "Объявление снова на проверке"
        : "Объявление обновлено"
      : pending
        ? "Объявление отправлено на проверку"
        : "Объявление опубликовано";

    const container = document.getElementById("view-sell");
    successNode = el("div", { class: "state" }, [
      el("div", { class: "state__icon", text: "✅" }),
      el("div", {
        class: "state__title",
        text: title,
      }),
      el("div", {
        class: "state__text",
        text: `${listing.kind_label}: ${listing.title} · ${formatListingPrice(listing)}`,
      }),
    ]);

    if (pending) {
      successNode.appendChild(
        el("div", {
          class: "state__text",
          text: "Администратор проверит объявление — после одобрения оно появится в каталоге.",
        }),
      );
    }

    if (photoFailures.length) {
      successNode.appendChild(
        el("div", {
          class: "field__error",
          text: `Объявление сохранено, но не все фотографии загрузились: ${photoFailures[0]}.`,
        }),
      );
      successNode.appendChild(
        el("div", {
          class: "state__text",
          text: "Фотографии можно добавить позже из объявления.",
        }),
      );
    }

    successNode.appendChild(
      el("button", {
        class: "button button--primary",
        type: "button",
        text: "Открыть объявление",
        onclick: () => {
          const id = listing.id;
          reset();
          openListing(id);
        },
      }),
    );
    if (isEdit) {
      successNode.appendChild(
        el("button", {
          class: "button button--ghost",
          type: "button",
          text: "В аккаунт",
          onclick: () => {
            reset();
            goAccount();
          },
        }),
      );
    } else {
      successNode.appendChild(
        el("button", {
          class: "button button--ghost",
          type: "button",
          text: "В каталог",
          onclick: () => {
            reset();
            goCatalog();
          },
        }),
      );
      successNode.appendChild(
        el("button", {
          class: "button button--ghost",
          type: "button",
          text: "Разместить ещё",
          onclick: () => reset(),
        }),
      );
    }
    container.appendChild(successNode);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function submit() {
    if (state.submitting) return;
    clearErrors();
    let valid = validateStep1().length === 0;
    valid = validateStep2().length === 0 && valid;
    valid = validateStep3().length === 0 && valid;
    if (!valid) {
      notify("Проверьте выделенные поля.", true);
      if (validateStep1().length) showStep(1);
      else if (validateStep2().length) showStep(2);
      return;
    }

    const isEdit = Boolean(state.editId);
    state.submitting = true;
    submitButton.disabled = true;
    backButton.disabled = true;
    cancelButton.disabled = true;
    setSubmitLabel(isEdit ? "Сохраняем…" : "Публикуем…");
    try {
      let listing;
      let photoFailures = [];

      if (isEdit) {
        listing = await api.updateListing(state.editId, buildFieldsPayload());
        for (const photoId of state.removedPhotoIds) {
          try {
            await api.deletePhoto(state.editId, photoId);
          } catch (error) {
            photoFailures.push(error.message || "не удалось удалить фото");
          }
        }
        if (state.files.length) {
          photoFailures = photoFailures.concat(await uploadPhotos(state.editId));
        }
      } else {
        listing = await api.createListing(buildPayload());
        if (state.files.length) {
          photoFailures = await uploadPhotos(listing.id);
        }
      }

      const pending = listing.moderation_status === "pending";
      setSubmitLabel(isEdit ? "Сохранено" : pending ? "Отправлено" : "Опубликовано");
      renderSuccess(listing, photoFailures, isEdit);
      notify(
        pending
          ? isEdit
            ? "Объявление отправлено на повторную проверку."
            : "Объявление отправлено на проверку."
          : isEdit
            ? "Объявление обновлено."
            : "Объявление опубликовано.",
      );
    } catch (error) {
      setSubmitLabel(isEdit ? "Сохранить" : "Опубликовать");
      applyServerErrors(error);
    } finally {
      state.submitting = false;
      submitButton.disabled = false;
      backButton.disabled = false;
      cancelButton.disabled = false;
    }
  }

  function reset() {
    for (const item of state.files) URL.revokeObjectURL(item.url);
    state.step = 1;
    state.kind = "sell";
    state.values = emptyValues();
    state.noBudget = false;
    state.priceNegotiable = false;
    state.conditionMode = "standard";
    state.files = [];
    state.existingPhotos = [];
    state.removedPhotoIds = [];
    state.editId = null;
    state.submitting = false;

    if (successNode) {
      successNode.remove();
      successNode = null;
    }
    form.hidden = false;
    wizardTitle.textContent = "Что размещаем?";
    titleInput.value = "";
    descriptionInput.value = "";
    priceInput.value = "";
    priceInput.disabled = false;
    noBudgetInput.checked = false;
    negotiableInput.checked = false;
    conditionTextInput.value = "";
    districtInput.value = "";
    photoInput.value = "";
    rulesCheckbox.checked = false;
    clearErrors();
    setSubmitLabel("Опубликовать");
    clear(previews);
    syncKindLabels();
    renderKind();
    renderConditionChips();
    renderDistricts();
    renderRules();
    renderPhotos();
    showStep(1);
  }

  function startEdit(listing) {
    reset();
    state.editId = listing.id;
    state.kind = listing.kind;
    state.values = {
      title: listing.title || "",
      description: listing.description || "",
      condition: listing.condition || "",
      conditionText: listing.condition_text || "",
      price: listing.price?.amount ? String(Number(listing.price.amount)) : "",
      district: listing.district || "",
    };
    state.conditionMode = listing.condition_text
      ? "custom"
      : listing.condition
        ? "standard"
        : "standard";
    state.priceNegotiable = Boolean(listing.price_negotiable);
    state.noBudget = listing.kind === "buy" && !listing.price;
    state.existingPhotos = (listing.photos || []).map((photo) => ({
      id: photo.id,
      url: photo.url,
    }));
    state.removedPhotoIds = [];
    state.files = [];

    titleInput.value = state.values.title;
    descriptionInput.value = state.values.description;
    priceInput.value = state.values.price;
    conditionTextInput.value = state.values.conditionText;
    negotiableInput.checked = state.priceNegotiable;
    noBudgetInput.checked = state.noBudget;
    wizardTitle.textContent = "Редактирование объявления";
    setSubmitLabel("Сохранить");
    form.hidden = false;
    if (successNode) {
      successNode.remove();
      successNode = null;
    }

    renderKind();
    renderConditionChips();
    syncKindLabels();
    renderDistricts();
    renderRules();
    renderPhotos();
    showStep(1);
  }

  function mount() {
    syncKindLabels();
    renderKind();
    renderConditionChips();
    renderDistricts();
    renderRules();
    renderPhotos();
    renderStepbar();
    showStep(1);
    photoInput.accept = limits().allowed_mime_types.join(",");

    titleInput.addEventListener("input", () => {
      state.values.title = titleInput.value;
    });
    descriptionInput.addEventListener("input", () => {
      state.values.description = descriptionInput.value;
    });
    priceInput.addEventListener("input", () => {
      state.values.price = priceInput.value;
    });
    districtInput.addEventListener("input", () => {
      state.values.district = districtInput.value;
      updatePhotoSummary();
    });
    noBudgetInput.addEventListener("change", () => {
      state.noBudget = noBudgetInput.checked;
      priceInput.disabled = state.noBudget;
      if (state.noBudget) {
        priceInput.value = "";
        state.values.price = "";
      }
      updatePhotoSummary();
    });
    negotiableInput.addEventListener("change", () => {
      state.priceNegotiable = negotiableInput.checked;
      if (state.priceNegotiable) {
        priceInput.value = "";
        state.values.price = "";
      }
      syncKindLabels();
      updatePhotoSummary();
    });
    conditionTextInput.addEventListener("input", () => {
      state.values.conditionText = conditionTextInput.value;
    });
    photoInput.addEventListener("change", (event) => {
      addFiles([...event.target.files]);
    });
    nextButton.addEventListener("click", () => {
      clearErrors();
      if (validateStep(state.step)) showStep(state.step + 1);
    });
    backButton.addEventListener("click", () => {
      clearErrors();
      showStep(Math.max(1, state.step - 1));
    });
    submitButton.addEventListener("click", submit);
    cancelButton.addEventListener("click", () => {
      if (onCancel) onCancel();
      else reset();
    });
  }

  return { mount, reset, startEdit };
}
