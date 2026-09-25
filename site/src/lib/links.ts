/** True for links that leave the site (http, mailto, etc.). */
export function isExternal(href: string): boolean {
  return /^(https?:|mailto:|tel:)/.test(href);
}
