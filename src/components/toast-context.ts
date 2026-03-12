import { createContext, useContext } from "react";

export type ToastType = "success" | "error" | "info";

export interface ToastCtx {
  toast: (message: string, type?: ToastType) => void;
}

export const ToastContext = createContext<ToastCtx>({ toast: () => {} });

export function useToast() {
  return useContext(ToastContext);
}
