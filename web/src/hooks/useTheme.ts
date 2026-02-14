import { useState, useEffect, useCallback } from 'react'

export type ThemeName = 'civitas' | 'dark'

const STORAGE_KEY = 'openclaw-theme'

const THEME_LABELS: Record<ThemeName, string> = {
  civitas: 'CIVITAS',
  dark: '暗色',
}

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeName>(() => {
    const saved = localStorage.getItem(STORAGE_KEY)
    return (saved === 'dark' ? 'dark' : 'civitas') as ThemeName
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem(STORAGE_KEY, theme)
  }, [theme])

  const setTheme = useCallback((t: ThemeName) => setThemeState(t), [])

  const toggle = useCallback(() => {
    setThemeState((prev) => (prev === 'civitas' ? 'dark' : 'civitas'))
  }, [])

  return { theme, setTheme, toggle, labels: THEME_LABELS }
}
