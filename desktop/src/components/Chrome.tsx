import type { ReactNode } from "react";
import {
  BookIcon,
  ChartIcon,
  CloseIcon,
  CommandIcon,
  ConstitutionIcon,
  EvolutionIcon,
  EvidenceIcon,
  LabIcon,
  MaximizeIcon,
  MinimizeIcon,
  OrganismIcon,
  PlaybookIcon,
  TissueIcon,
  TruthIcon,
} from "./Icons";
import { executionSealPresentation } from "../state";
import type { ConnectionPhase, ViewId } from "../types";
import { VIEW_DEFINITIONS } from "../viewMetadata";

interface TitleBarProps {
  readonly connection: ConnectionPhase;
  readonly onMinimize: () => void;
  readonly onMaximize: () => void;
  readonly onClose: () => void;
}

const connectionTone = (connection: ConnectionPhase): string => {
  if (connection === "CONNECTED") {
    return "nominal";
  }
  if (connection === "CONNECTING") {
    return "notice";
  }
  return "critical";
};

export const TitleBar = ({ connection, onMinimize, onMaximize, onClose }: TitleBarProps) => (
  <header className="titlebar">
    <div className="titlebar__drag pywebview-drag-region">
      <div className="wordmark" aria-label="DOPEY">
        <span className="wordmark__mark"><i aria-hidden="true" />D/</span>
        <span className="wordmark__name">DOPEY</span>
      </div>
      <span className="titlebar__section">SOVEREIGN PAPER RESEARCH INSTRUMENT</span>
      <span className={`link-state link-state--${connectionTone(connection)}`}>
        <i aria-hidden="true" />
        LOCAL LINK {connection}
      </span>
    </div>
    <div className="window-controls" aria-label="Window controls">
      <button aria-label="Minimize window" className="window-control" onClick={onMinimize} type="button">
        <MinimizeIcon size={15} />
      </button>
      <button aria-label="Toggle maximize window" className="window-control" onClick={onMaximize} type="button">
        <MaximizeIcon size={13} />
      </button>
      <button
        aria-label="Hide DOPEY to system tray"
        className="window-control window-control--close"
        onClick={onClose}
        title="Hide to system tray"
        type="button"
      >
        <CloseIcon size={14} />
      </button>
    </div>
  </header>
);

const navigationIcons: Readonly<Record<ViewId, ReactNode>> = {
  command: <CommandIcon size={20} />,
  market: <TissueIcon size={20} />,
  chart: <ChartIcon size={20} />,
  lab: <LabIcon size={20} />,
  playbook: <PlaybookIcon size={20} />,
  organisms: <OrganismIcon size={20} />,
  truth: <TruthIcon size={20} />,
  evidence: <EvidenceIcon size={20} />,
  evolution: <EvolutionIcon size={20} />,
  paper: <BookIcon size={20} />,
  constitution: <ConstitutionIcon size={20} />,
};

interface NavigationProps {
  readonly activeView: ViewId;
  readonly executionSeal: string | null;
  readonly issueCount: number;
  readonly onSelect: (view: ViewId) => void;
}

export const Navigation = ({ activeView, executionSeal, issueCount, onSelect }: NavigationProps) => {
  const seal = executionSealPresentation(executionSeal);
  return (
    <aside className="navigation">
      <span className="navigation__rail-label">WORKSPACES</span>
      <nav aria-label="Primary navigation" className="navigation__items">
        {VIEW_DEFINITIONS.map((item, index) => (
          <div className="navigation__entry" key={item.id}>
          {index === 0 || VIEW_DEFINITIONS[index - 1]?.group !== item.group ? <span className="navigation__group">{item.group}</span> : null}
          <button
            aria-controls="workbench-stage"
            aria-current={activeView === item.id ? "page" : undefined}
            aria-label={`${item.label}, ${item.shortcut}`}
            className={`navigation__item${activeView === item.id ? " navigation__item--active" : ""}`}
            onClick={() => onSelect(item.id)}
            title={`${item.label} // ${item.shortcut}`}
            type="button"
          >
            <span className="navigation__index">{String(index + 1).padStart(2, "0")}</span>
            <span className="navigation__icon">{navigationIcons[item.id]}</span>
            <span className="navigation__label">{item.shorthand}</span>
            {item.id === "command" && issueCount > 0 ? <span className="navigation__alert">{issueCount}</span> : null}
          </button>
          </div>
        ))}
      </nav>
      <div
        className={`navigation__footer navigation__footer--${seal.state}`}
        title={`${seal.label}; paper-research authority only`}
      >
        <ConstitutionIcon size={18} />
        <span>{seal.state === "sealed" ? "SEALED" : seal.label}</span>
      </div>
    </aside>
  );
};
