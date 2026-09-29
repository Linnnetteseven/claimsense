import { useEffect, useId, useRef, useState } from "react";
import PropTypes from "prop-types";

/**
 * Text input with code suggestions (ICD-11 or SHA interventions).
 * Accessible combobox: arrow keys move, Enter picks, Esc closes. Typing a code
 * directly still works; suggestions only help.
 */
export default function CodeSearchInput({ id, value, onChange, onPick, search, placeholder, className, ariaLabel, onKeyDown }) {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState([]);
  const [active, setActive] = useState(-1);
  const listId = useId();
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);

  const lookup = (text) => {
    clearTimeout(timer.current);
    if (text.trim().length < 2) {
      setOptions([]);
      setOpen(false);
      return;
    }
    timer.current = setTimeout(async () => {
      try {
        const found = await search(text);
        setOptions(found);
        setActive(-1);
        setOpen(found.length > 0);
      } catch {
        setOptions([]);
        setOpen(false);
      }
    }, 200);
  };

  const pick = (option) => {
    onPick(option);
    setOpen(false);
  };

  const handleKeyDown = (e) => {
    if (open && e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, options.length - 1));
    } else if (open && e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (open && e.key === "Enter" && active >= 0) {
      e.preventDefault();
      pick(options.at(active));
    } else if (open && e.key === "Escape") {
      e.stopPropagation();
      setOpen(false);
    } else {
      onKeyDown?.(e);
    }
  };

  return (
    <div className="relative">
      <input
        id={id}
        type="text"
        role="combobox"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
        autoComplete="off"
        value={value ?? ""}
        placeholder={placeholder}
        onChange={(e) => {
          onChange(e.target.value);
          lookup(e.target.value);
        }}
        onKeyDown={handleKeyDown}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        className={className}
      />
      {open && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 w-full max-h-64 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-lg text-xs"
        >
          {options.map((option, i) => (
            <li
              key={option.code}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(option);
              }}
              className={`px-3 py-2 cursor-pointer ${
                i === active ? "bg-teal-50 dark:bg-teal-950/40" : "hover:bg-slate-50 dark:hover:bg-slate-800"
              }`}
            >
              <span className="font-mono font-semibold text-slate-800 dark:text-slate-100">{option.code}</span>
              <span className="ml-2 text-slate-600 dark:text-slate-300">{option.title}</span>
              {option.note && <span className="block text-[11px] text-teal-800 dark:text-teal-300">{option.note}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

CodeSearchInput.propTypes = {
  id: PropTypes.string,
  value: PropTypes.string,
  onChange: PropTypes.func.isRequired,
  onPick: PropTypes.func.isRequired,
  search: PropTypes.func.isRequired,
  placeholder: PropTypes.string,
  className: PropTypes.string,
  ariaLabel: PropTypes.string,
  onKeyDown: PropTypes.func,
};
