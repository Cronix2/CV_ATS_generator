"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";

interface AutocompleteInputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  suggestions: string[];
  placeholder?: string;
  required?: boolean;
  type?: string;
}

export function AutocompleteInput({
  label,
  value,
  onChange,
  suggestions,
  placeholder,
  required,
  type = "text",
}: AutocompleteInputProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [filtered, setFiltered] = useState<string[]>([]);
  const [highlightIndex, setHighlightIndex] = useState(-1);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const filterSuggestions = useCallback(
    (input: string) => {
      if (!input.trim()) {
        setFiltered([]);
        return;
      }
      const lower = input.toLowerCase();
      const results = suggestions
        .filter((s) => s.toLowerCase().includes(lower))
        .slice(0, 8);
      setFiltered(results);
      setIsOpen(results.length > 0);
      setHighlightIndex(-1);
    },
    [suggestions]
  );

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (highlightIndex >= 0 && listRef.current) {
      const item = listRef.current.children[highlightIndex] as HTMLElement;
      item?.scrollIntoView({ block: "nearest" });
    }
  }, [highlightIndex]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (!isOpen) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightIndex((prev) => (prev < filtered.length - 1 ? prev + 1 : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightIndex((prev) => (prev > 0 ? prev - 1 : filtered.length - 1));
    } else if (e.key === "Enter" && highlightIndex >= 0) {
      e.preventDefault();
      selectItem(filtered[highlightIndex]);
    } else if (e.key === "Escape") {
      setIsOpen(false);
    }
  }

  function selectItem(item: string) {
    onChange(item);
    setIsOpen(false);
    setFiltered([]);
  }

  return (
    <div ref={wrapperRef} className="relative">
      <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
        {label}
        {required && <span className="text-rose-500 ml-1">*</span>}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          filterSuggestions(e.target.value);
        }}
        onFocus={() => value && filterSuggestions(value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        required={required}
        className={cn(
          "w-full px-4 py-3 rounded-xl border bg-white dark:bg-zinc-900",
          "border-zinc-200 dark:border-zinc-700",
          "text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500",
          "focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500",
          "transition-all duration-200"
        )}
        autoComplete="off"
      />
      {isOpen && filtered.length > 0 && (
        <ul
          ref={listRef}
          className={cn(
            "absolute z-50 w-full mt-1 py-1 rounded-xl border shadow-xl max-h-56 overflow-auto",
            "bg-white dark:bg-zinc-800 border-zinc-200 dark:border-zinc-700"
          )}
        >
          {filtered.map((item, i) => (
            <li
              key={item}
              onClick={() => selectItem(item)}
              className={cn(
                "px-4 py-2.5 cursor-pointer text-sm transition-colors",
                "text-zinc-700 dark:text-zinc-200",
                i === highlightIndex && "bg-indigo-50 dark:bg-indigo-500/20 text-indigo-700 dark:text-indigo-300"
              )}
            >
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
