/** Catalog view: search, filters, sorting, infinite loading and states. */

import { clear, chipButton, el, setPressed, show } from "../dom.js";
import { formatCount, formatListingPrice, parsePriceInput, timeAgo } from "../format.js";

const SORT_LABELS = {
  newest: "Сначала новые",
  price_asc: "Сначала дешёвые",
  price_desc: "Сначала дорогие",
};

const PAGE_SIZE = 20;

function emptyFilters() {
  return {
    q: "",
    kind: "",
    district: "",
    condition: "",
    minPrice: "",
    maxPrice: "",
    sort: "newest",
  };
}

export function createCatalogView({ api, getMeta, openListing, openLink, notify }) {
  const state = {
    items: [],
    total: 0,
    offset: 0,
    hasMore: false,
    loading: false,
    loaded: false,
    error: null,
    requestId: 0,
    filters: emptyFilters(),
  };

  const els = {
    search: document.getElementById("search-input"),
    clearSearch: document.getElementById("clear-search"),
    kindChips: document.getElementById("kind-chips"),
    count: document.getElementById("catalog-count"),
    sortButton: document.getElementById("sort-button"),
    filtersButton: document.getElementById("filters-button"),
    filtersBadge: document.getElementById("filters-badge"),
    adSlot: document.getElementById("ad-slot"),
    stateBox: document.getElementById("catalog-state"),
    grid: document.getElementById("catalog-grid"),
    loadMore: document.getElementById("load-more-button"),
    sentinel: document.getElementById("catalog-sentinel"),
    filtersSheet: document.getElementById("filters-sheet"),
    filtersBody: document.getElementById("filters-body"),
    filtersApply: document.getElementById("filters-apply"),
    filtersReset: document.getElementById("filters-reset"),
    filtersClose: document.getElementById("filters-close"),
  };

  let searchTimer = null;
  let draft = emptyFilters();
  let observer = null;

  function placeholder() {
    return el("div", { class: "card__placeholder", text: "Нет фото" });
  }

  function card(item) {
    const media = el("div", { class: "card__media" });
    if (item.cover_photo?.url) {
      const image = el("img", {
        src: item.cover_photo.url,
        alt: item.title,
        loading: "lazy",
        decoding: "async",
      });
      image.addEventListener("error", () => {
        image.remove();
        media.prepend(placeholder());
      });
      media.appendChild(image);
    } else {
      media.appendChild(placeholder());
    }
    media.appendChild(el("span", { class: "card__type", text: item.kind_label }));
    if (item.photo_count > 1) {
      media.appendChild(
        el("span", { class: "card__status", text: `${item.photo_count} фото` }),
      );
    }

    const body = el("div", { class: "card__body" }, [
      el("h3", { class: "card__title", text: item.title }),
      el("div", { class: "card__price", text: formatListingPrice(item) }),
    ]);
    if (item.condition_label) {
      body.appendChild(
        el("div", { class: "card__meta" }, [el("span", { text: item.condition_label })]),
      );
    }
    body.appendChild(
      el("div", { class: "card__meta" }, [
        el("span", { text: item.district }),
        el("span", { class: "card__dot", text: timeAgo(item.created_at) }),
      ]),
    );

    return el(
      "button",
      {
        class: "card",
        type: "button",
        onclick: () => openListing(item.id),
        attrs: { "aria-label": `${item.kind_label}: ${item.title}` },
      },
      [media, body],
    );
  }

  function renderSkeletons() {
    clear(els.grid);
    for (let index = 0; index < 6; index += 1) {
      els.grid.appendChild(
        el("div", { class: "skeleton" }, [
          el("div", { class: "skeleton__media" }),
          el("div", { class: "skeleton__line" }),
          el("div", { class: "skeleton__line skeleton__line--short" }),
        ]),
      );
    }
  }

  function renderStateBox(kind) {
    clear(els.stateBox);
    let icon = "🔍";
    let title = "Ничего не найдено";
    let text = "Попробуйте изменить запрос или сбросить фильтры.";
    let actionLabel = "Сбросить фильтры";
    let action = resetFilters;

    if (kind === "error") {
      icon = "⚠️";
      title = "Не удалось загрузить каталог";
      text = state.error?.message || "Проверьте соединение и попробуйте снова.";
      actionLabel = "Повторить";
      action = () => load(true);
    } else if (kind === "auth") {
      icon = "🔒";
      title = "Нужен вход через Telegram";
      text = "Откройте приложение кнопкой в боте: данные авторизации передаются только там.";
      actionLabel = "Повторить";
      action = () => load(true);
    }

    els.stateBox.appendChild(el("div", { class: "state__icon", text: icon }));
    els.stateBox.appendChild(el("div", { class: "state__title", text: title }));
    els.stateBox.appendChild(el("div", { class: "state__text", text }));
    els.stateBox.appendChild(
      el("button", {
        class: "button button--ghost",
        type: "button",
        text: actionLabel,
        onclick: action,
      }),
    );
    show(els.stateBox, true);
  }

  function renderAll() {
    updateControls();

    const showSkeleton = state.loading && state.items.length === 0;
    if (showSkeleton) {
      show(els.stateBox, false);
      renderSkeletons();
      show(els.loadMore, false);
      return;
    }

    if (state.error && state.items.length === 0) {
      clear(els.grid);
      renderStateBox(state.error.status === 401 ? "auth" : "error");
      show(els.loadMore, false);
      return;
    }

    if (state.loaded && state.items.length === 0) {
      clear(els.grid);
      renderStateBox("empty");
      show(els.loadMore, false);
      return;
    }

    show(els.stateBox, false);
    clear(els.grid);
    for (const item of state.items) els.grid.appendChild(card(item));
    show(els.loadMore, state.hasMore && !state.loading);
  }

  function activeFilterCount() {
    const { district, condition, minPrice, maxPrice } = state.filters;
    return [district, condition, minPrice, maxPrice].filter(Boolean).length;
  }

  function updateControls() {
    els.count.textContent = state.loaded
      ? formatCount(state.total, "объявление", "объявления", "объявлений")
      : "";
    els.sortButton.textContent = SORT_LABELS[state.filters.sort] || SORT_LABELS.newest;
    els.clearSearch.hidden = !els.search.value;
    const active = activeFilterCount();
    els.filtersBadge.hidden = active === 0;
    els.filtersBadge.textContent = String(active);
    for (const chip of els.kindChips.querySelectorAll(".chip")) {
      setPressed(chip, chip.dataset.value === state.filters.kind);
    }
  }

  async function load(reset) {
    if (state.loading && !reset) return;
    if (reset) {
      state.items = [];
      state.offset = 0;
      state.error = null;
      state.loaded = true;
    }
    state.loading = true;
    const requestId = (state.requestId += 1);
    renderAll();
    try {
      const data = await api.listListings({
        ...state.filters,
        limit: PAGE_SIZE,
        offset: state.offset,
      });
      if (requestId !== state.requestId) return;
      state.items = reset ? data.items : state.items.concat(data.items);
      state.total = data.total;
      state.hasMore = data.has_more;
      state.offset += data.items.length;
      state.error = null;
    } catch (error) {
      if (requestId !== state.requestId) return;
      state.error = error;
      if (reset) state.items = [];
    } finally {
      if (requestId === state.requestId) {
        state.loading = false;
        renderAll();
      }
    }
  }

  function resetFilters() {
    state.filters = emptyFilters();
    els.search.value = "";
    draft = { ...state.filters };
    load(true);
  }

  function buildFiltersBody() {
    clear(els.filtersBody);
    const meta = getMeta();

    const sortBlock = el("div", { class: "filter-block" }, [
      el("span", { class: "filter-block__title", text: "Сортировка" }),
      el(
        "div",
        { class: "chips chips--wrap" },
        Object.entries(SORT_LABELS).map(([value, label]) =>
          chipButton({
            label,
            value,
            active: draft.sort === value,
            onClick: (event) => {
              draft.sort = value;
              for (const chip of event.currentTarget.parentElement.querySelectorAll(".chip")) {
                setPressed(chip, chip === event.currentTarget);
              }
            },
          }),
        ),
      ),
    ]);

    const districtSelect = el("select", { class: "input input--select", id: "filter-district" }, [
      el("option", { value: "", text: "Любой район" }),
      ...meta.districts.map((district) =>
        el("option", {
          value: district,
          text: district,
          selected: draft.district === district,
        }),
      ),
    ]);
    districtSelect.value = draft.district;
    const districtBlock = el("div", { class: "filter-block" }, [
      el("label", { class: "filter-block__title", for: "filter-district", text: "Район" }),
      districtSelect,
    ]);

    const conditionOptions = [{ value: "", label: "Любое" }, ...meta.conditions];
    const conditionBlock = el("div", { class: "filter-block" }, [
      el("span", { class: "filter-block__title", text: "Состояние" }),
      el(
        "div",
        { class: "chips chips--wrap" },
        conditionOptions.map((option) =>
          chipButton({
            label: option.label,
            value: option.value,
            active: draft.condition === option.value,
            onClick: (event) => {
              draft.condition = option.value;
              for (const chip of event.currentTarget.parentElement.querySelectorAll(".chip")) {
                setPressed(chip, chip === event.currentTarget);
              }
            },
          }),
        ),
      ),
    ]);

    const priceBlock = el("div", { class: "filter-block" }, [
      el("span", { class: "filter-block__title", text: "Цена, ₽" }),
      el("div", { class: "filter-prices" }, [
        el("input", {
          class: "input",
          id: "filter-price-min",
          inputmode: "decimal",
          placeholder: "От",
          value: draft.minPrice,
          maxlength: 12,
        }),
        el("input", {
          class: "input",
          id: "filter-price-max",
          inputmode: "decimal",
          placeholder: "До",
          value: draft.maxPrice,
          maxlength: 12,
        }),
      ]),
    ]);

    els.filtersBody.appendChild(sortBlock);
    els.filtersBody.appendChild(districtBlock);
    els.filtersBody.appendChild(conditionBlock);
    els.filtersBody.appendChild(priceBlock);
  }

  function openFilters() {
    draft = { ...state.filters };
    buildFiltersBody();
    show(els.filtersSheet, true);
  }

  function closeFilters() {
    show(els.filtersSheet, false);
  }

  function applyFilters() {
    const minRaw = document.getElementById("filter-price-min").value;
    const maxRaw = document.getElementById("filter-price-max").value;
    const minPrice = parsePriceInput(minRaw);
    const maxPrice = parsePriceInput(maxRaw);
    if (minRaw.trim() && !minPrice) {
      notify("Минимальная цена должна быть положительным числом.", true);
      return;
    }
    if (maxRaw.trim() && !maxPrice) {
      notify("Максимальная цена должна быть положительным числом.", true);
      return;
    }
    if (minPrice && maxPrice && Number(minPrice) > Number(maxPrice)) {
      notify("Минимальная цена не может быть больше максимальной.", true);
      return;
    }
    state.filters = {
      ...state.filters,
      sort: draft.sort,
      district: document.getElementById("filter-district").value,
      condition: draft.condition,
      minPrice: minPrice || "",
      maxPrice: maxPrice || "",
    };
    closeFilters();
    load(true);
  }

  function renderKindChips() {
    clear(els.kindChips);
    const meta = getMeta();
    const options = [{ value: "", label: "Все" }, ...meta.kinds];
    for (const option of options) {
      els.kindChips.appendChild(
        chipButton({
          label: option.label,
          value: option.value,
          active: state.filters.kind === option.value,
          onClick: () => {
            state.filters.kind = option.value;
            updateControls();
            load(true);
          },
        }),
      );
    }
  }

  function renderAd() {
    const ad = getMeta()?.ad;
    if (!ad) {
      show(els.adSlot, false);
      return;
    }
    clear(els.adSlot);
    const content = el("div", { class: "ad__content" }, [
      el("span", { class: "ad__label", text: "Реклама" }),
      el("span", { class: "ad__title", text: ad.title }),
    ]);
    if (ad.text) content.appendChild(el("span", { class: "ad__text", text: ad.text }));

    const adBox = el("div", { class: "ad" });
    if (ad.image_url) {
      const image = el("img", {
        class: "ad__image",
        src: ad.image_url,
        alt: "",
        loading: "lazy",
        referrerpolicy: "no-referrer",
      });
      image.addEventListener("error", () => image.remove());
      adBox.appendChild(image);
    }
    content.appendChild(
      el("button", {
        class: "ad__link",
        type: "button",
        text: ad.button_text || "Подробнее",
        onclick: () => openLink(ad.link_url),
      }),
    );
    adBox.appendChild(content);
    els.adSlot.appendChild(adBox);
    show(els.adSlot, true);
  }

  function mount() {
    renderKindChips();
    renderAd();

    els.search.addEventListener("input", () => {
      els.clearSearch.hidden = !els.search.value;
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => {
        state.filters.q = els.search.value.trim();
        load(true);
      }, 350);
    });
    els.clearSearch.addEventListener("click", () => {
      els.search.value = "";
      state.filters.q = "";
      updateControls();
      load(true);
    });
    els.sortButton.addEventListener("click", openFilters);
    els.filtersButton.addEventListener("click", openFilters);
    els.filtersClose.addEventListener("click", closeFilters);
    els.filtersApply.addEventListener("click", applyFilters);
    els.filtersReset.addEventListener("click", () => {
      draft = emptyFilters();
      buildFiltersBody();
    });
    els.filtersSheet.addEventListener("click", (event) => {
      if (event.target === els.filtersSheet) closeFilters();
    });
    els.loadMore.addEventListener("click", () => load(false));

    if ("IntersectionObserver" in window) {
      observer = new IntersectionObserver(
        (entries) => {
          const visible = entries.some((entry) => entry.isIntersecting);
          if (visible && state.hasMore && !state.loading) load(false);
        },
        { rootMargin: "300px 0px" },
      );
      observer.observe(els.sentinel);
    }
  }

  return {
    mount,
    refresh: () => load(true),
    state,
  };
}
