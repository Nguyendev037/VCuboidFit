"use client";

import { useEffect, useRef } from "react";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Hộp xác nhận dựa trên phần tử <dialog> gốc (không dùng window.confirm). */
export function ConfirmDialog({ open, title, message, confirmLabel, onConfirm, onCancel }: ConfirmDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby="confirm-dialog-title"
      onCancel={(e) => { e.preventDefault(); onCancel(); }}
      className="m-auto w-[min(92vw,26rem)] rounded-lg border border-slate-200 p-5 shadow-xl backdrop:bg-slate-900/40"
    >
      <h3 id="confirm-dialog-title" className="text-sm font-semibold">{title}</h3>
      <p className="mt-2 text-xs text-slate-600">{message}</p>
      <div className="mt-4 flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="min-h-9 rounded px-3 text-xs hover:bg-slate-100">Huỷ</button>
        <button type="button" onClick={onConfirm} className="min-h-9 rounded bg-rose-700 px-3 text-xs font-medium text-white hover:bg-rose-800">{confirmLabel}</button>
      </div>
    </dialog>
  );
}
