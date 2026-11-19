import { useEffect, useId, useState, type ReactNode } from "react";
import { AlertCircle, ChevronDown } from "lucide-react";
import { formatInput, parseNumber } from "../../lib/format";
import { cn } from "../../lib/utils";

interface FieldFrameProps {
  htmlFor?: string;
  label: ReactNode;
  unit?: string;
  help?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
}

export function FieldFrame({
  htmlFor,
  label,
  unit,
  help,
  error,
  required,
  children,
  className,
  action,
}: FieldFrameProps) {
  return (
    <div className={cn("field", className)}>
      <label className="field-label" htmlFor={htmlFor}>
        <span>
          {label}
          {required ? <span className="ml-0.5 text-[var(--danger)]">*</span> : null}
        </span>
        {unit ? <span className="field-unit">{unit}</span> : action}
      </label>
      {children}
      {error ? (
        <span className="field-error" id={htmlFor ? `${htmlFor}-error` : undefined} role="alert">
          <AlertCircle size={12} className="mt-0.5 shrink-0" aria-hidden />
          {error}
        </span>
      ) : help ? (
        <span className="field-hint" id={htmlFor ? `${htmlFor}-help` : undefined}>
          {help}
        </span>
      ) : null}
    </div>
  );
}

export interface NumberFieldProps {
  label: ReactNode;
  value: number | null;
  onChange: (value: number | null) => void;
  unit?: string;
  min?: number;
  max?: number;
  step?: number;
  help?: ReactNode;
  error?: ReactNode;
  disabled?: boolean;
  readOnly?: boolean;
  placeholder?: string;
  required?: boolean;
  className?: string;
  digits?: number;
  id?: string;
}

function isIntermediate(text: string): boolean {
  return /^[+-]?[.,]?$/.test(text.trim());
}

export function NumberField({
  label,
  value,
  onChange,
  unit,
  min,
  max,
  step = 1,
  help,
  error,
  disabled,
  readOnly,
  placeholder = "—",
  required,
  className,
  digits = 6,
  id,
}: NumberFieldProps) {
  const autoId = useId();
  const inputId = id ?? `num-${autoId}`;
  const [text, setText] = useState(() => formatInput(value, digits));
  const [focused, setFocused] = useState(false);
  const [localInvalid, setLocalInvalid] = useState(false);

  useEffect(() => {
    if (!focused) {
      setText(formatInput(value, digits));
      setLocalInvalid(false);
    }
  }, [value, digits, focused]);

  const handleChange = (raw: string) => {
    setText(raw);
    if (isIntermediate(raw)) {
      setLocalInvalid(false);
      return;
    }
    const parsed = parseNumber(raw);
    if (parsed === null) {
      setLocalInvalid(false);
      onChange(null);
      return;
    }
    if (Number.isNaN(parsed)) {
      setLocalInvalid(true);
      return;
    }
    setLocalInvalid(false);
    onChange(parsed);
  };

  const hasError = Boolean(error) || localInvalid;

  return (
    <FieldFrame
      htmlFor={inputId}
      label={label}
      unit={unit}
      help={help}
      error={error ?? (localInvalid ? "Geçerli bir sayı girin (örn. 12,5)." : undefined)}
      required={required}
      className={className}
    >
      <input
        id={inputId}
        inputMode="decimal"
        className="input numeric"
        value={text}
        placeholder={placeholder}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        readOnly={readOnly}
        required={required}
        aria-invalid={hasError || undefined}
        aria-describedby={hasError && `${inputId}-error` ? `${inputId}-error` : help ? `${inputId}-help` : undefined}
        onFocus={() => setFocused(true)}
        onBlur={() => {
          setFocused(false);
          setText(formatInput(value, digits));
          setLocalInvalid(false);
        }}
        onChange={(event) => handleChange(event.target.value)}
      />
    </FieldFrame>
  );
}

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectFieldProps {
  label: ReactNode;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  unit?: string;
  help?: ReactNode;
  error?: ReactNode;
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
  className?: string;
  id?: string;
}

export function SelectField({
  label,
  value,
  onChange,
  options,
  unit,
  help,
  error,
  placeholder,
  disabled,
  required,
  className,
  id,
}: SelectFieldProps) {
  const autoId = useId();
  const selectId = id ?? `sel-${autoId}`;
  return (
    <FieldFrame
      htmlFor={selectId}
      label={label}
      unit={unit}
      help={help}
      error={error}
      required={required}
      className={className}
    >
      <div className="relative">
        <select
          id={selectId}
          className="select"
          value={value}
          disabled={disabled}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${selectId}-error` : help ? `${selectId}-help` : undefined}
          onChange={(event) => onChange(event.target.value)}
        >
          {placeholder ? <option value="">{placeholder}</option> : null}
          {options.map((option) => (
            <option key={option.value} value={option.value} disabled={option.disabled}>
              {option.label}
            </option>
          ))}
        </select>
        <ChevronDown
          size={14}
          className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[var(--text-faint)]"
          aria-hidden
        />
      </div>
    </FieldFrame>
  );
}

export interface TextFieldProps {
  label: ReactNode;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  help?: ReactNode;
  error?: ReactNode;
  disabled?: boolean;
  required?: boolean;
  className?: string;
  type?: "text" | "date" | "email" | "search";
  id?: string;
  maxLength?: number;
}

export function TextField({
  label,
  value,
  onChange,
  placeholder,
  help,
  error,
  disabled,
  required,
  className,
  type = "text",
  id,
  maxLength,
}: TextFieldProps) {
  const autoId = useId();
  const inputId = id ?? `txt-${autoId}`;
  return (
    <FieldFrame
      htmlFor={inputId}
      label={label}
      help={help}
      error={error}
      required={required}
      className={className}
    >
      <input
        id={inputId}
        type={type}
        className="input"
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        required={required}
        maxLength={maxLength}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${inputId}-error` : help ? `${inputId}-help` : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
    </FieldFrame>
  );
}

export function CheckboxRow({
  checked,
  onChange,
  label,
  hint,
  badge,
  className,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  hint?: ReactNode;
  badge?: ReactNode;
  className?: string;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3 transition-colors",
        checked && "border-[color-mix(in_srgb,var(--success)_45%,var(--border))] bg-[var(--success-bg)]",
        className,
      )}
    >
      <input
        id={id}
        type="checkbox"
        className="checkbox mt-0.5"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <label htmlFor={id} className="min-w-0 flex-1 cursor-pointer">
        <span className="block text-[12.5px] font-medium leading-snug text-[var(--text-soft)]">{label}</span>
        {hint ? <span className="mt-0.5 block text-[11px] leading-snug text-[var(--text-faint)]">{hint}</span> : null}
      </label>
      {badge ? <div className="shrink-0">{badge}</div> : null}
    </div>
  );
}

export function FieldGrid({
  children,
  cols = 2,
  className,
}: {
  children: ReactNode;
  cols?: 1 | 2 | 3 | 4;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "grid gap-3",
        cols === 1 && "grid-cols-1",
        cols === 2 && "grid-cols-1 sm:grid-cols-2",
        cols === 3 && "grid-cols-1 sm:grid-cols-2 xl:grid-cols-3",
        cols === 4 && "grid-cols-2 xl:grid-cols-4",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function ReadonlyValue({
  label,
  value,
  unit,
  hint,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  unit?: string;
  hint?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("field", className)}>
      <span className="field-label">
        <span>{label}</span>
        {unit ? <span className="field-unit">{unit}</span> : null}
      </span>
      <div className="input numeric flex items-center justify-end text-[13.5px] text-[var(--text-soft)]" aria-readonly>
        {value}
      </div>
      {hint ? <span className="field-hint">{hint}</span> : null}
    </div>
  );
}
