/** Frappe translation function — available globally via window.__ */
declare function __(msg: string, replace?: Record<string, string> | string[], context?: string): string

interface Window {
  posPageSetProfile?: (profileName: string) => void
  posPageClearProfile?: () => void
}
