/** API client. All requests are same-origin and carry the Telegram initData. */

import { getInitData } from "./telegram.js";

const REQUEST_TIMEOUT_MS = 20000;

export class ApiError extends Error {
  constructor(message, { status = 0, code = "unknown", fields = [] } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

function buildQuery(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

async function parseError(response) {
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  const error = payload?.error || {};
  const message =
    typeof error.message === "string" && error.message
      ? error.message
      : "Не удалось выполнить запрос. Попробуйте ещё раз.";
  return new ApiError(message, {
    status: response.status,
    code: typeof error.code === "string" ? error.code : "http_error",
    fields: Array.isArray(payload?.fields) ? payload.fields : [],
  });
}

export class ApiClient {
  async request(path, { method = "GET", body, formData, auth = true } = {}) {
    const headers = { Accept: "application/json" };
    if (auth) {
      const initData = getInitData();
      if (initData) headers.Authorization = `tma ${initData}`;
    }
    let payload;
    if (formData) {
      payload = formData;
    } else if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    let response;
    try {
      response = await fetch(path, {
        method,
        headers,
        body: payload,
        signal: controller.signal,
        credentials: "same-origin",
        cache: "no-store",
      });
    } catch (error) {
      if (error?.name === "AbortError") {
        throw new ApiError("Сервер не ответил вовремя. Проверьте соединение.", {
          code: "timeout",
        });
      }
      throw new ApiError("Нет соединения с сервером. Проверьте интернет.", {
        code: "network",
      });
    } finally {
      window.clearTimeout(timer);
    }

    if (!response.ok) throw await parseError(response);
    if (response.status === 204) return null;
    try {
      return await response.json();
    } catch {
      throw new ApiError("Сервер вернул некорректный ответ.", { code: "bad_response" });
    }
  }

  getMe() {
    return this.request("/api/me");
  }

  getMeta() {
    return this.request("/api/meta");
  }

  listListings(filters) {
    return this.request(
      `/api/listings${buildQuery({
        q: filters.q,
        kind: filters.kind,
        district: filters.district,
        condition: filters.condition,
        min_price: filters.minPrice,
        max_price: filters.maxPrice,
        sort: filters.sort,
        limit: filters.limit,
        offset: filters.offset,
      })}`,
    );
  }

  getListing(id) {
    return this.request(`/api/listings/${encodeURIComponent(id)}`);
  }

  createListing(payload) {
    return this.request("/api/listings", { method: "POST", body: payload });
  }

  updateStatus(id, status) {
    return this.request(`/api/listings/${encodeURIComponent(id)}/status`, {
      method: "PATCH",
      body: { status },
    });
  }

  moderateListing(id, action, reason) {
    const body = reason ? { action, reason } : { action };
    return this.request(`/api/listings/${encodeURIComponent(id)}/moderation`, {
      method: "POST",
      body,
    });
  }

  addFavorite(id) {
    return this.request(`/api/listings/${encodeURIComponent(id)}/favorite`, {
      method: "PUT",
    });
  }

  removeFavorite(id) {
    return this.request(`/api/listings/${encodeURIComponent(id)}/favorite`, {
      method: "DELETE",
    });
  }

  getFavorites() {
    return this.request("/api/me/favorites");
  }

  updateListing(id, payload) {
    return this.request(`/api/listings/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: payload,
    });
  }

  createComplaint(listingId, payload) {
    return this.request(
      `/api/listings/${encodeURIComponent(listingId)}/complaints`,
      { method: "POST", body: payload },
    );
  }

  myListings() {
    return this.request("/api/me/listings");
  }

  uploadPhoto(listingId, file) {
    const formData = new FormData();
    formData.append("file", file, file.name || "photo");
    return this.request(`/api/listings/${encodeURIComponent(listingId)}/photos`, {
      method: "POST",
      formData,
    });
  }

  deletePhoto(listingId, photoId) {
    return this.request(
      `/api/listings/${encodeURIComponent(listingId)}/photos/${encodeURIComponent(photoId)}`,
      { method: "DELETE" },
    );
  }
}
