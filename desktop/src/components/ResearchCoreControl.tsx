import { useEffect, useRef, useState } from "react";
import type { AutomationScheduleState, CorePhase, InstrumentMode, LlmProviderControlState, LlmProviderId } from "../types";
import { ResearchRoutingControl } from "./ResearchRoutingControl";

const HOLD_DURATION_MS = 1400;
const HOLD_TICK_MS = 28;

interface ResearchCoreControlProps {
  readonly phase: CorePhase;
  readonly enabled: boolean | null;
  readonly validated: boolean | null;
  readonly canToggle: boolean;
  readonly busy: boolean;
  readonly detail: string;
  readonly schedules: readonly AutomationScheduleState[];
  readonly providerControl: LlmProviderControlState;
  readonly onInstrumentMode: (mode: InstrumentMode) => Promise<void>;
  readonly onProvider: (provider: LlmProviderId, enabled: boolean) => Promise<void>;
  readonly onOpenRouterKey: (apiKey: string) => Promise<void>;
  readonly onToggle: (enabled: boolean) => Promise<void>;
}

const scheduleTone = (schedule: AutomationScheduleState): string => {
  if (
    schedule.present !== true ||
    schedule.identityVerified !== true ||
    schedule.actionVerified !== true
  ) {
    return "fault";
  }
  if (schedule.enabled === true) {
    return "active";
  }
  if (schedule.enabled === false) {
    return "idle";
  }
  return "unverified";
};

const scheduleLabel = (schedule: AutomationScheduleState): string => {
  if (schedule.name === "DOPEY_AccelerationCycle") {
    return "ACCELERATION CYCLE";
  }
  if (schedule.name === "DOPEY_DailyRitual") {
    return "DAILY RITUAL";
  }
  return schedule.name.replaceAll("_", " ").toUpperCase();
};

export const ResearchCoreControl = ({
  phase,
  enabled,
  validated,
  canToggle,
  busy,
  detail,
  schedules,
  providerControl,
  onInstrumentMode,
  onProvider,
  onOpenRouterKey,
  onToggle,
}: ResearchCoreControlProps) => {
  const [pendingTarget, setPendingTarget] = useState<boolean | null>(null);
  const [holdProgress, setHoldProgress] = useState(0);
  const holdStartedAt = useRef<number | null>(null);
  const holdTimer = useRef<number | null>(null);
  const activePointerId = useRef<number | null>(null);
  const confirmationBaselineEnabled = useRef<boolean | null>(null);
  const triggerButton = useRef<HTMLButtonElement | null>(null);
  const holdButton = useRef<HTMLButtonElement | null>(null);
  const cancelButton = useRef<HTMLButtonElement | null>(null);
  const requestedTarget = phase === "FAULT" ? false : enabled !== true;

  const clearHold = (): void => {
    if (holdTimer.current !== null) {
      window.clearInterval(holdTimer.current);
      holdTimer.current = null;
    }
    holdStartedAt.current = null;
    activePointerId.current = null;
    setHoldProgress(0);
  };

  const restoreTriggerFocus = (): void => {
    window.requestAnimationFrame(() => triggerButton.current?.focus());
  };

  const closeConfirmation = (restoreFocus: boolean): void => {
    clearHold();
    confirmationBaselineEnabled.current = null;
    setPendingTarget(null);
    if (restoreFocus) {
      restoreTriggerFocus();
    }
  };

  useEffect(() => clearHold, []);

  useEffect(() => {
    if (
      pendingTarget !== null &&
      confirmationBaselineEnabled.current !== enabled
    ) {
      closeConfirmation(true);
    }
  }, [enabled, pendingTarget]);

  useEffect(() => {
    if (pendingTarget === null) {
      return;
    }
    const focusFrame = window.requestAnimationFrame(() => holdButton.current?.focus());
    const cancelOnEscape = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeConfirmation(true);
      }
    };
    document.addEventListener("keydown", cancelOnEscape);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener("keydown", cancelOnEscape);
    };
  }, [pendingTarget]);

  const completeHold = async (targetEnabled: boolean): Promise<void> => {
    clearHold();
    confirmationBaselineEnabled.current = null;
    setPendingTarget(null);
    await onToggle(targetEnabled);
    restoreTriggerFocus();
  };

  const startHold = (): void => {
    const frozenTarget = pendingTarget;
    if (
      frozenTarget === null ||
      !canToggle ||
      busy ||
      holdStartedAt.current !== null
    ) {
      return;
    }
    holdStartedAt.current = performance.now();
    holdTimer.current = window.setInterval(() => {
      const startedAt = holdStartedAt.current;
      if (startedAt === null) {
        return;
      }
      const elapsed = performance.now() - startedAt;
      const progress = Math.min(1, elapsed / HOLD_DURATION_MS);
      setHoldProgress(progress);
      if (progress >= 1) {
        void completeHold(frozenTarget);
      }
    }, HOLD_TICK_MS);
  };

  const openConfirmation = (): void => {
    if (!canToggle || busy || phase === "DRAINING") {
      return;
    }
    clearHold();
    confirmationBaselineEnabled.current = enabled;
    setPendingTarget(requestedTarget);
  };

  const handleHoldKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>): void => {
    if ((event.key === " " || event.key === "Enter") && !event.repeat) {
      event.preventDefault();
      startHold();
    }
  };

  const handleHoldKeyUp = (event: React.KeyboardEvent<HTMLButtonElement>): void => {
    if (event.key === " " || event.key === "Enter") {
      event.preventDefault();
      clearHold();
    }
  };

  const handlePointerDown = (event: React.PointerEvent<HTMLButtonElement>): void => {
    if (!event.isPrimary || event.button !== 0) {
      return;
    }
    activePointerId.current = event.pointerId;
    event.currentTarget.setPointerCapture(event.pointerId);
    startHold();
  };

  const handlePointerEnd = (event: React.PointerEvent<HTMLButtonElement>): void => {
    if (!event.isPrimary || activePointerId.current !== event.pointerId) {
      return;
    }
    clearHold();
  };

  const handleDialogKeyDown = (event: React.KeyboardEvent<HTMLDivElement>): void => {
    if (event.key !== "Tab") {
      return;
    }
    const first = holdButton.current;
    const last = cancelButton.current;
    if (first === null || last === null) {
      return;
    }
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const phaseTone = phase === "FAULT"
    ? "fault"
    : phase === "RUNNING" || phase === "ON"
      ? "active"
      : "idle";

  return (
    <section className={`core-control core-control--${phaseTone}`} aria-labelledby="research-core-title">
      <div className="core-control__header">
        <div>
          <span className="eyebrow">MASTER CONTROL / PAPER AUTOMATION</span>
          <h2 id="research-core-title">Automation schedules</h2>
        </div>
        <span className={`phase-readout phase-readout--${phaseTone}`}>{busy ? "TRANSITION" : phase}</span>
      </div>

      <div className="core-control__mechanism">
        <button
          aria-checked={enabled === true}
          aria-describedby="core-control-detail"
          aria-expanded={pendingTarget !== null}
          aria-haspopup="dialog"
          aria-label={`${requestedTarget ? "Enable" : "Disable"} future paper automation schedules`}
          className="mechanical-switch"
          disabled={!canToggle || busy || phase === "DRAINING"}
          onClick={openConfirmation}
          ref={triggerButton}
          role="switch"
          type="button"
        >
          <span className="mechanical-switch__rail" aria-hidden="true">
            <span className="mechanical-switch__contact mechanical-switch__contact--off">0</span>
            <span className={`mechanical-switch__lever${enabled === true ? " mechanical-switch__lever--on" : ""}`}>
              <i />
              <b />
            </span>
            <span className="mechanical-switch__contact mechanical-switch__contact--on">I</span>
          </span>
        </button>
        <div className="core-control__annotations">
          <span>AUTHORITY</span>
          <strong>FUTURE PAPER AUTOMATION ONLY</strong>
          <span>AGGREGATE VALIDATION</span>
          <strong>{validated === null ? "NOT REPORTED" : validated ? "VERIFIED" : "BLOCKED"}</strong>
        </div>
      </div>

      <ResearchRoutingControl
        busy={busy}
        canConfigure={canToggle}
        onInstrumentMode={onInstrumentMode}
        onOpenRouterKey={onOpenRouterKey}
        onProvider={onProvider}
        state={providerControl}
      />

      <div className="core-control__schedules" aria-label="Aggregate paper automation schedule state">
        {schedules.length === 0 ? (
          <span className="core-control__schedule-empty">SCHEDULE ROSTER UNVERIFIED</span>
        ) : schedules.map((schedule) => (
          <div className={`core-control__schedule core-control__schedule--${scheduleTone(schedule)}`} key={schedule.id}>
            <span>{scheduleLabel(schedule)}</span>
            <strong>{schedule.enabled === true ? "ENABLED" : schedule.enabled === false ? "DISABLED" : "UNVERIFIED"}</strong>
            <em>{schedule.state?.toUpperCase() ?? "STATE UNREPORTED"}</em>
          </div>
        ))}
      </div>

      <p className="core-control__detail" id="core-control-detail">
        {detail}
      </p>

      {pendingTarget === null ? null : (
        <div
          aria-describedby="core-confirm-description"
          aria-labelledby="core-confirm-title"
          aria-modal="true"
          className="core-confirm"
          onKeyDown={handleDialogKeyDown}
          role="dialog"
        >
          <div className="core-confirm__copy">
            <span className="eyebrow">DELIBERATE AGGREGATE TRANSITION</span>
            <strong id="core-confirm-title">
              {pendingTarget ? "ENABLE PAPER AUTOMATION" : "DISABLE + DRAIN PAPER AUTOMATION"}
            </strong>
            <p id="core-confirm-description">
              {pendingTarget
                ? "Enables future paper automation schedules. It grants no live execution authority."
                : "Disables future paper automation schedules and drains any active cycle without terminating it."}
            </p>
          </div>
          <button
            className="hold-control"
            onKeyDown={handleHoldKeyDown}
            onKeyUp={handleHoldKeyUp}
            onPointerCancel={handlePointerEnd}
            onPointerDown={handlePointerDown}
            onPointerLeave={handlePointerEnd}
            onPointerUp={handlePointerEnd}
            ref={holdButton}
            style={{ "--hold-progress": `${Math.round(holdProgress * 100)}%` } as React.CSSProperties}
            type="button"
          >
            <span>PRESS + HOLD</span>
            <small>{Math.round(holdProgress * 100)}%</small>
          </button>
          <button
            className="core-confirm__cancel"
            onClick={() => closeConfirmation(true)}
            ref={cancelButton}
            type="button"
          >
            CANCEL
          </button>
        </div>
      )}
    </section>
  );
};
