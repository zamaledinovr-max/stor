/** Formatting helpers (money, time, numbers). */

const priceFormatter = new Intl.NumberFormat("ru-RU", {
  maximumFractionDigits: 2,
});

const dateFormatter = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

const timeFormatter = new Intl.DateTimeFormat("ru-RU", {
  hour: "2-digit",
  minute: "2-digit",
});

const relativeFormatter = new Intl.RelativeTimeFormat("ru-RU", { numeric: "auto" });

export function formatPrice(price) {
  if (!price) return "Цена не указана";
  const amount = Number.parseFloat(price.amount);
  if (!Number.isFinite(amount)) return "Цена не указана";
  const suffix = price.currency === "RUB" ? "₽" : price.currency || "";
  return `${priceFormatter.format(amount)} ${suffix}`.trim();
}

export function formatBudget(price) {
  if (!price) return "Бюджет не указан";
  return `до ${formatPrice(price)}`;
}

export function formatListingPrice(listing) {
  if (listing.kind === "sell" && listing.price_negotiable) {
    return "Договорная";
  }
  if (!listing.price) {
    return listing.kind === "buy" ? "Бюджет не указан" : "Цена не указана";
  }
  return listing.kind === "buy" ? formatBudget(listing.price) : formatPrice(listing.price);
}

export function formatDate(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return dateFormatter.format(date);
}

export function formatDateTime(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return `${dateFormatter.format(date)}, ${timeFormatter.format(date)}`;
}

/** Relative time like "3 часа назад" from an ISO-8601 UTC timestamp. */
export function timeAgo(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const diffSeconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (diffSeconds < 60) return "только что";
  const minutes = Math.floor(diffSeconds / 60);
  if (minutes < 60) return relativeFormatter.format(-minutes, "minute");
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return relativeFormatter.format(-hours, "hour");
  const days = Math.floor(hours / 24);
  if (days < 7) return relativeFormatter.format(-days, "day");
  return formatDate(iso);
}

export function pluralize(count, one, few, many) {
  const value = Math.abs(count) % 100;
  const last = value % 10;
  if (value > 10 && value < 20) return many;
  if (last > 1 && last < 5) return few;
  if (last === 1) return one;
  return many;
}

export function formatCount(count, one, few, many) {
  return `${priceFormatter.format(count)} ${pluralize(count, one, few, many)}`;
}

/** Parse a price entered as text with spaces/commas; returns a decimal string. */
export function parsePriceInput(value) {
  const raw = String(value ?? "")
    .replace(/\s+/g, "")
    .replace(",", ".");
  if (!raw) return null;
  if (!/^\d{1,10}(\.\d{1,2})?$/.test(raw)) return null;
  const number = Number.parseFloat(raw);
  if (!Number.isFinite(number) || number <= 0) return null;
  return number.toFixed(2);
}
