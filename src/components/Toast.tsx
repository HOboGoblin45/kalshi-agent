import { useState, useCallback, type ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ToastContext, type ToastType } from "./toast-context";

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

let _id = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = useCallback((message: string, type: ToastType = "info") => {
    const id = ++_id;
    setToasts((t) => [...t, { id, message, type }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3000);
  }, []);

  const prefixes = { success: "[OK]", error: "[ERR]", info: "[INFO]" };
  const colors = {
    success: "border-accent-green text-accent-green",
    error: "border-accent-red text-accent-red",
    info: "border-accent-gold text-accent-gold",
  };

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed top-3 right-3 z-[100] flex flex-col gap-1.5 pointer-events-none">
        <AnimatePresence>
          {toasts.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, x: 40 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 40 }}
              className={`pointer-events-auto px-3 py-2 border bg-bg-base text-[11px] font-bold ${colors[t.type]}`}
            >
              {prefixes[t.type]} {t.message}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}
