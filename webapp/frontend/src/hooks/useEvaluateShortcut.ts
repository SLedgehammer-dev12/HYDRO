import { useEffect, useRef } from "react";

/**
 * Sayfa seviyesinde değerlendirme kısayolu (Ctrl/Cmd + Enter).
 * Uygulama kabuğu `hydro:evaluate` olayını yayınlar.
 */
export function useEvaluateShortcut(handler: () => void, enabled = true): void {
  const ref = useRef(handler);
  ref.current = handler;

  useEffect(() => {
    const listener = () => {
      if (enabled) ref.current();
    };
    window.addEventListener("hydro:evaluate", listener);
    return () => window.removeEventListener("hydro:evaluate", listener);
  }, [enabled]);
}
