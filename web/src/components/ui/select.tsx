"use client";
import * as React from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export type SelectOption = {
  value: string;
  label: string;
  disabled?: boolean;
};

type SelectProps = {
  /** Accessible name for the trigger and its listbox. */
  label: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  /** Shown when no option matches the current value. */
  placeholder?: string;
  size?: "sm" | "md";
  disabled?: boolean;
  className?: string;
  menuClassName?: string;
};

const TRIGGER_SIZE = {
  sm: "h-8 pl-2.5 pr-7 text-[13px]",
  md: "h-10 pl-3 pr-9 text-[14px]",
} as const;
const CHEVRON_SIZE = { sm: "right-2 size-3.5", md: "right-3 size-4" } as const;

/**
 * The product's own listbox. A native `<select>` hands its popup to the operating
 * system, so the open menu would wear the desktop's typography instead of this
 * workspace's hairlines. This is a real listbox: arrow keys, Home/End, Enter,
 * Escape, outside click and focus return all behave as expected.
 */
export function Select({
  label,
  value,
  options,
  onChange,
  placeholder,
  size = "sm",
  disabled = false,
  className,
  menuClassName,
}: SelectProps) {
  const id = React.useId();
  const [open, setOpen] = React.useState(false);
  const [active, setActive] = React.useState(0);
  const wrap = React.useRef<HTMLDivElement>(null);
  const trigger = React.useRef<HTMLButtonElement>(null);
  const list = React.useRef<HTMLUListElement>(null);
  const selectedIndex = options.findIndex((option) => option.value === value);
  const selected = selectedIndex >= 0 ? options[selectedIndex] : undefined;

  const close = React.useCallback((refocus = true) => {
    setOpen(false);
    if (refocus) trigger.current?.focus();
  }, []);

  const openMenu = () => {
    setActive(selectedIndex >= 0 ? selectedIndex : 0);
    setOpen(true);
  };

  const choose = (index: number) => {
    const option = options[index];
    if (!option || option.disabled) return;
    onChange(option.value);
    close();
  };

  React.useEffect(() => {
    if (!open) return;
    list.current?.focus();
    const onPointerDown = (event: PointerEvent) => {
      if (!wrap.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  // Keep the active row visible while arrowing through a long list.
  React.useEffect(() => {
    if (!open) return;
    const row = list.current?.querySelector<HTMLElement>(`[data-index="${active}"]`);
    row?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  function onTriggerKeyDown(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openMenu();
    }
  }

  function onListKeyDown(event: React.KeyboardEvent<HTMLUListElement>) {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setActive((index) => Math.min(index + 1, options.length - 1));
        break;
      case "ArrowUp":
        event.preventDefault();
        setActive((index) => Math.max(index - 1, 0));
        break;
      case "Home":
        event.preventDefault();
        setActive(0);
        break;
      case "End":
        event.preventDefault();
        setActive(options.length - 1);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        choose(active);
        break;
      case "Escape":
        event.preventDefault();
        close();
        break;
      case "Tab":
        setOpen(false);
        break;
      default:
        break;
    }
  }

  return (
    <div ref={wrap} className={cn("relative", className)}>
      <button
        ref={trigger}
        id={`${id}-trigger`}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? `${id}-listbox` : undefined}
        aria-label={label}
        disabled={disabled}
        onClick={() => (open ? close() : openMenu())}
        onKeyDown={onTriggerKeyDown}
        className={cn(
          "flex w-full items-center gap-2 rounded-md border border-input bg-canvas text-left text-ink",
          "transition-colors duration-150 hover:bg-surface-soft",
          "focus-visible:border-primary focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-primary/15",
          "disabled:pointer-events-none disabled:opacity-50",
          TRIGGER_SIZE[size],
        )}
      >
        <span className="min-w-0 flex-1 truncate">{selected?.label ?? placeholder ?? ""}</span>
        <ChevronDown
          aria-hidden
          strokeWidth={1.5}
          className={cn(
            "pointer-events-none absolute top-1/2 -translate-y-1/2 text-muted-foreground transition-transform duration-150",
            CHEVRON_SIZE[size],
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <ul
          ref={list}
          id={`${id}-listbox`}
          role="listbox"
          aria-labelledby={`${id}-trigger`}
          tabIndex={-1}
          onKeyDown={onListKeyDown}
          className={cn(
            "absolute left-0 z-50 mt-1 max-h-64 w-max min-w-full max-w-[22rem] overflow-y-auto",
            "rounded-lg border border-hairline bg-popover py-1 text-[14px] outline-none shadow-pop",
            menuClassName,
          )}
        >
          {options.map((option, index) => {
            const isSelected = option.value === value;
            return (
              <li
                key={option.value || `__blank-${index}`}
                data-index={index}
                role="option"
                aria-selected={isSelected}
                aria-disabled={option.disabled || undefined}
                onClick={() => choose(index)}
                onPointerMove={() => setActive(index)}
                className={cn(
                  "flex cursor-pointer items-center gap-2 px-2.5 py-1.5",
                  "text-ink transition-colors duration-100",
                  index === active && "bg-surface-card",
                  option.disabled && "pointer-events-none opacity-45",
                  isSelected && "font-medium",
                )}
              >
                <span className="min-w-0 flex-1 truncate">{option.label}</span>
                {isSelected && <Check className="size-3.5 shrink-0 text-primary" strokeWidth={1.75} />}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
