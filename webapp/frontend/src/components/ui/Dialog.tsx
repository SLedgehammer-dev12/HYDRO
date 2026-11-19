import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { Button, IconButton } from "./Button";
import { cn } from "../../lib/utils";

export function Modal({
  open,
  onClose,
  dismissible = true,
  title,
  description,
  children,
  footer,
  className,
}: {
  open: boolean;
  onClose: () => void;
  dismissible?: boolean;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const headingId = useId();
  const descId = useId();
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open) {
      if (!dialog.open) {
        dialog.showModal();
      }
    } else if (dialog.open) {
      dialog.close();
    }
  }, [open]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    const handleClose = () => {
      dialog.returnValue = "";
      onCloseRef.current();
    };
    const handleCancel = (e: Event) => {
      if (!dismissible) {
        e.preventDefault();
      }
    };
    dialog.addEventListener("close", handleClose);
    dialog.addEventListener("cancel", handleCancel);

    // Safari / <dialog> light-dismiss fallback when closedby="any" is unsupported
    let cleanupFallback: (() => void) | undefined;
    if (
      dismissible &&
      typeof HTMLDialogElement !== "undefined" &&
      !("closedBy" in HTMLDialogElement.prototype)
    ) {
      let pressedOutside = false;
      const outside = (e: PointerEvent) => {
        const r = dialog.getBoundingClientRect();
        return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
      };
      const onPointerDown = (e: PointerEvent) => {
        pressedOutside = e.target === dialog && outside(e);
      };
      const onPointerUp = (e: PointerEvent) => {
        if (pressedOutside && e.target === dialog && outside(e) && dialog.open) {
          dialog.close();
        }
        pressedOutside = false;
      };
      dialog.addEventListener("pointerdown", onPointerDown);
      dialog.addEventListener("pointerup", onPointerUp);
      cleanupFallback = () => {
        dialog.removeEventListener("pointerdown", onPointerDown);
        dialog.removeEventListener("pointerup", onPointerUp);
      };
    }

    return () => {
      dialog.removeEventListener("close", handleClose);
      dialog.removeEventListener("cancel", handleCancel);
      cleanupFallback?.();
    };
  }, [open, dismissible]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <dialog
      ref={dialogRef}
      aria-labelledby={headingId}
      aria-describedby={description ? descId : undefined}
      {...({ closedby: dismissible ? "any" : "none" } as Record<string, unknown>)}
      className={cn("modal-dialog", className)}
    >
      <header className="flex items-start justify-between gap-3 border-b border-[var(--border)] px-5 py-4">
        <div className="min-w-0">
          <h2 id={headingId} className="text-[19px] font-bold text-[var(--text)]">
            {title}
          </h2>
          {description ? (
            <p id={descId} className="mt-1 text-[13px] text-[var(--text-muted)]">
              {description}
            </p>
          ) : null}
        </div>
        <IconButton label="Kapat" onClick={onClose}>
          <X size={15} aria-hidden />
        </IconButton>
      </header>
      <div className="px-5 py-4">{children}</div>
      {footer ? (
        <footer className="flex flex-wrap justify-end gap-2 border-t border-[var(--border)] px-5 py-3.5">
          {footer}
        </footer>
      ) : null}
    </dialog>,
    document.body,
  );
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Onayla",
  cancelLabel = "Vazgeç",
  danger = false,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const cancelBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open && danger) {
      requestAnimationFrame(() => cancelBtnRef.current?.focus());
    }
  }, [open, danger]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button ref={cancelBtnRef} variant="ghost" onClick={onClose}>
            {cancelLabel}
          </Button>
          <Button
            variant={danger ? "danger" : "primary"}
            onClick={() => {
              onConfirm();
              onClose();
            }}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="text-[12.5px] leading-relaxed text-[var(--text-muted)]">{message}</div>
    </Modal>
  );
}
