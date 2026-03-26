'use client';

import React, { createContext, useContext } from 'react';
import ErrorBoundary from './ErrorBoundary';
import ToastContainer from './Toast';
import { useToast, type ToastVariant } from '../hooks/useToast';

interface ToastContextValue {
  addToast: (message: string, variant?: ToastVariant, duration?: number) => string;
}

const ToastContext = createContext<ToastContextValue>({
  addToast: () => '',
});

export function useToastContext() {
  return useContext(ToastContext);
}

export default function ClientProviders({ children }: { children: React.ReactNode }) {
  const { toasts, addToast, dismiss } = useToast();

  return (
    <ToastContext.Provider value={{ addToast }}>
      <ErrorBoundary>
        {children}
      </ErrorBoundary>
      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}
