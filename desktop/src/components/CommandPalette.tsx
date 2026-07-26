import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { CloseIcon, SearchIcon } from "./Icons";
import { VIEW_DEFINITIONS } from "../viewMetadata";
import type { ViewDefinition } from "../viewMetadata";
import type { ViewId } from "../types";

interface CommandPaletteProps {
  readonly activeView: ViewId;
  readonly open: boolean;
  readonly onClose: () => void;
  readonly onSelect: (view: ViewId) => void;
}

const normalizedQuery = (query: string): string => query.trim().toLocaleLowerCase();

const queryScore = (view: ViewDefinition, query: string): number | null => {
  const normalized = normalizedQuery(query);
  if (normalized.length === 0) {
    return 0;
  }
  const id = view.id.toLocaleLowerCase();
  const label = view.label.toLocaleLowerCase();
  const title = view.title.toLocaleLowerCase();
  const shorthand = view.shorthand.toLocaleLowerCase();
  const description = view.description.toLocaleLowerCase();
  if (id === normalized || label === normalized || title === normalized || shorthand === normalized) {
    return 0;
  }
  if (id.startsWith(normalized) || label.startsWith(normalized) || title.startsWith(normalized) || shorthand.startsWith(normalized)) {
    return 1;
  }
  if (id.includes(normalized) || label.includes(normalized) || title.includes(normalized) || shorthand.includes(normalized)) {
    return 2;
  }
  return description.includes(normalized) ? 3 : null;
};

const matchingViews = (query: string): readonly ViewDefinition[] =>
  VIEW_DEFINITIONS
    .map((view) => ({ score: queryScore(view, query), view }))
    .filter((candidate): candidate is { readonly score: number; readonly view: ViewDefinition } => candidate.score !== null)
    .sort((left, right) => left.score - right.score)
    .map((candidate) => candidate.view);

export const CommandPalette = ({ activeView, open, onClose, onSelect }: CommandPaletteProps) => {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const filteredViews = useMemo(() => matchingViews(query), [query]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) {
      return;
    }
    if (open && !dialog.open) {
      dialog.showModal();
      window.requestAnimationFrame(() => inputRef.current?.focus());
    }
    if (!open && dialog.open) {
      dialog.close();
    }
    return () => {
      if (dialog.open) {
        dialog.close();
      }
    };
  }, [open]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setHighlightedIndex(0);
    }
  }, [open]);

  useEffect(() => {
    setHighlightedIndex(0);
  }, [query]);

  const selectView = (view: ViewId): void => {
    onSelect(view);
    onClose();
  };

  const onDialogKeyDown = (event: KeyboardEvent<HTMLDialogElement>): void => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (filteredViews.length === 0) {
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlightedIndex((current) => (current + 1) % filteredViews.length);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlightedIndex((current) => (current - 1 + filteredViews.length) % filteredViews.length);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const selected = filteredViews[highlightedIndex];
      if (selected !== undefined) {
        selectView(selected.id);
      }
    }
  };

  return (
    <dialog
      aria-labelledby="workspace-palette-title"
      aria-modal="true"
      className="command-palette"
      id="workspace-palette"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
      onKeyDown={onDialogKeyDown}
      ref={dialogRef}
    >
      <div className="command-palette__surface">
        <header className="command-palette__header">
          <span className="command-palette__mark" aria-hidden="true">D/</span>
          <div>
            <span>WORKSPACE NAVIGATOR</span>
            <h2 id="workspace-palette-title">Move through DOPEY</h2>
          </div>
          <button aria-label="Close workspace navigator" onClick={onClose} type="button">
            <kbd>ESC</kbd>
            <CloseIcon size={15} />
          </button>
        </header>
        <label className="command-palette__search" htmlFor="workspace-search">
          <SearchIcon size={18} />
          <span>SEARCH</span>
          <input
            aria-controls="workspace-results"
            autoComplete="off"
            id="workspace-search"
            onChange={(event) => setQuery(event.currentTarget.value)}
            placeholder="Search workspaces, evidence, charts, controls..."
            ref={inputRef}
            spellCheck={false}
            type="search"
            value={query}
          />
          <kbd>CTRL K</kbd>
        </label>
        <div className="command-palette__results" id="workspace-results" role="listbox">
          {filteredViews.length === 0 ? (
            <div className="command-palette__empty">
              <strong>No workspace found</strong>
              <span>Try a shorter research term.</span>
            </div>
          ) : filteredViews.map((view, index) => {
            const highlighted = index === highlightedIndex;
            const active = view.id === activeView;
            return (
              <button
                aria-selected={highlighted}
                className={`command-palette__result${highlighted ? " is-highlighted" : ""}${active ? " is-active" : ""}`}
                key={view.id}
                onClick={() => selectView(view.id)}
                onMouseEnter={() => setHighlightedIndex(index)}
                role="option"
                type="button"
              >
                <span className="command-palette__result-index">{String(index + 1).padStart(2, "0")}</span>
                <span className="command-palette__result-copy">
                  <strong>{view.title}</strong>
                  <small>{view.description}</small>
                </span>
                {active ? <em>CURRENT</em> : <kbd>{view.shortcut}</kbd>}
              </button>
            );
          })}
        </div>
        <footer className="command-palette__footer">
          <span><kbd>↑</kbd><kbd>↓</kbd> MOVE</span>
          <span><kbd>ENTER</kbd> OPEN</span>
          <strong>PAPER RESEARCH // LIVE EXECUTION BLOCKED</strong>
        </footer>
      </div>
    </dialog>
  );
};
