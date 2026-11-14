/** Fired on `window` after the owner saves a new shop name, so the sidebar shows it straight away instead of at the next 20-second check. */
export const SHOP_RENAMED = 'swara:shop-renamed'

/** Mirror of the server's rule, so the form can say what is wrong before saving. The server stays the judge of which characters are allowed. */
export const cleanShopName = (v: string) => v.replace(/\s+/g, ' ').trim()
export const shopNameProblem = (v: string): string | null => {
  const n = cleanShopName(v)
  return n.length < 2 || n.length > 80 ? 'Use 2 to 80 characters.' : null
}
