import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./styles.css";

/**
 * R3F v9 her Canvas mount'unda `new THREE.Clock()` kullanıyor; Three r187 bu
 * sınıfı deprecated ilan ediyor. Uyarı uygulama hatası değil ve yalnızca
 * `@react-three/fiber` sürümü yükseltildiğinde kalkacak. Konsolu temiz tutmak
 * için yalnızca bu tek mesajı, yalnızca dev modda filtreliyoruz; diğer tüm
 * uyarı ve hatalar aynen geçer.
 */
if (import.meta.env.DEV) {
  const originalWarn = console.warn.bind(console);
  const clockWarning = "THREE.Clock: This module has been deprecated";
  console.warn = (...args: Parameters<typeof console.warn>) => {
    if (typeof args[0] === "string" && args[0].startsWith(clockWarning)) return;
    originalWarn(...args);
  };
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
