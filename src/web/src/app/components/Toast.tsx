'use client';

import React from 'react';
import type { Toast as ToastType, ToastVariant } from '../hooks/useToast';

const VARIANT_STYLES: Record<ToastVariant, string> = {
  success:
    'bg-[var(--success-bg)] text-[var(--success)] border-[var(--success)]',
  error:
    'bg-[var(--error-bg)] text-[var(--error)] border-[var(--error)]',
  info:
    'bg-[var(--accent-bg)] text-[var(--accent)] border-[var(--accent)]',
};

const VARIANT_ICONS: Record<ToastVariant, string> = {
  success: '✓',
  error: '✕',
  info: 'ℹ',
};

interface ToastContainerProps {
  toasts: ToastType[];
  onDismiss: (id: string) => void;
}

export default function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  if (toasts.length === 0) return null;

  return (
    <div
      aria-live="polite"
      aria-label="Notifications"
      className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 max-w-sm w-full pointer-events-none"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role="status"
          className={`pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-lg border shadow-lg text-sm font-medium chat-message-enter ${VARIANT_STYLES[toast.variant]}`}
        >
          <span className="text-base leading-none shrink-0" aria-hidden="true">
            {VARIANT_ICONS[toast.variant]}
          </span>
          <span className="flex-1 min-w-0">{toast.message}</span>
          <button
            onClick={() => onDismiss(toast.id)}
            aria-label="Dismiss notification"
            className="shrink-0 p-1 rounded hover:bg-black/10 transition-colors text-current opacity-60 hover:opacity-100"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
