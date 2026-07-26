import { useCallback, useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { BridgeUnavailableError, readControlState } from "../bridge";
import { disconnectedModel, failedModel, normalizeSnapshot } from "../state";
import type { ControlModel } from "../types";

export type OperatorErrorKind = "mutation" | "refresh" | "window";

export interface OperatorErrorState {
  readonly kind: OperatorErrorKind;
  readonly message: string;
}

export interface UseSnapshotPollResult {
  readonly model: ControlModel;
  readonly refreshing: boolean;
  readonly refresh: () => Promise<void>;
  readonly operatorError: OperatorErrorState | null;
  readonly setOperatorError: Dispatch<SetStateAction<OperatorErrorState | null>>;
}

export const useSnapshotPoll = (refreshIntervalMs: number): UseSnapshotPollResult => {
  const [model, setModel] = useState<ControlModel>(() => disconnectedModel("Awaiting local control bridge."));
  const [refreshing, setRefreshing] = useState(false);
  const [operatorError, setOperatorError] = useState<OperatorErrorState | null>(null);
  const refreshInFlight = useRef(false);

  const refresh = useCallback(async (): Promise<void> => {
    if (refreshInFlight.current) {
      return;
    }
    refreshInFlight.current = true;
    setRefreshing(true);
    try {
      const raw = await readControlState();
      setModel(normalizeSnapshot(raw));
      setOperatorError((current) => current?.kind === "mutation" ? current : null);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Unknown local control bridge error.";
      setModel(failedModel(error instanceof BridgeUnavailableError ? "UNAVAILABLE" : "ERROR", message));
      setOperatorError((current) => current?.kind === "mutation"
        ? current
        : { kind: "refresh", message });
    } finally {
      refreshInFlight.current = false;
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    const onBridgeReady = (): void => {
      void refresh();
    };
    window.addEventListener("pywebviewready", onBridgeReady);
    void refresh();
    const refreshTimer = window.setInterval(() => void refresh(), refreshIntervalMs);
    return () => {
      window.removeEventListener("pywebviewready", onBridgeReady);
      window.clearInterval(refreshTimer);
    };
  }, [refresh, refreshIntervalMs]);

  return { model, refreshing, refresh, operatorError, setOperatorError };
};
