"use client";

import React, { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

interface TooltipProps {
  label: string;
  content: string;
  className?: string;
  dark?: boolean;
}

export function Tooltip({ label, content, className = "", dark = false }: TooltipProps) {
  const id = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0, below: false });

  const updatePosition = useCallback(() => {
    const rect = buttonRef.current?.getBoundingClientRect();
    if (!rect) return;
    const below = rect.top < 120 || rect.bottom + 150 < window.innerHeight;
    const halfWidth = Math.min(160, (window.innerWidth - 24) / 2);
    setPosition({
      top: below ? rect.bottom + 8 : rect.top - 8,
      left: Math.max(halfWidth + 12, Math.min(window.innerWidth - halfWidth - 12, rect.left + rect.width / 2)),
      below,
    });
  }, []);

  useEffect(() => {
    if (!open) return;
    updatePosition();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open, updatePosition]);

  const tooltip = open && typeof document !== "undefined"
    ? createPortal(
        <span
          id={id}
          role="tooltip"
          className={`fixed z-[100] w-max max-w-[min(20rem,calc(100vw-24px))] -translate-x-1/2 rounded-md px-3 py-2 text-left text-xs font-normal leading-relaxed shadow-lg ${dark ? "border border-white/15 bg-slate-900 text-white" : "border border-slate-200 bg-white text-slate-700"}`}
          style={{ top: position.top, left: position.left, transform: `translate(-50%, ${position.below ? "0" : "-100%"})` }}
        >
          {content}
        </span>,
        document.body,
      )
    : null;

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        aria-label={`Giải thích: ${label}`}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onMouseEnter={() => { updatePosition(); setOpen(true); }}
        onMouseLeave={() => { if (document.activeElement !== buttonRef.current) setOpen(false); }}
        onFocus={() => { updatePosition(); setOpen(true); }}
        onBlur={() => setOpen(false)}
        onClick={(event) => { event.preventDefault(); event.stopPropagation(); updatePosition(); setOpen(true); }}
        className={`inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-current/30 text-[10px] font-semibold leading-none hover:bg-current/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500 ${className}`}
      >
        ?
      </button>
      {tooltip}
    </>
  );
}
