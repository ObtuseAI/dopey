import type { LiveBranchState } from "../types";
import { displayLabel, formatTimestamp } from "../state";

interface LiveBranchControlProps {
  readonly branch: LiveBranchState;
  readonly busy: boolean;
  readonly onOptionsExecution: (enabled: boolean) => Promise<void>;
}

const money = (value: number | null): string => value === null
  ? "—"
  : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);

export const LiveBranchControl = ({ branch, busy, onOptionsExecution }: LiveBranchControlProps) => {
  const connected = branch.authenticated === true;
  const optionsOn = branch.optionsExecutionEnabled === true;
  return (
    <section className={`live-branch${connected ? " is-connected" : " is-pending"}`} aria-label="DOPEY Live Branch">
      <div className="live-branch__pulse" aria-hidden="true"><i /><i /><i /></div>
      <header>
        <div><span>ROBINHOOD AGENTIC / OFFICIAL MCP</span><h2>Live Branch</h2></div>
        <strong className={connected ? "is-live" : "is-pending"}>{connected ? "● LIVE" : "○ CONFIGURED"}</strong>
      </header>
      <div className="live-branch__metrics">
        <div><span>ACCOUNT</span><strong>{displayLabel(branch.accountLabel)}</strong><em>{displayLabel(branch.accountType)}</em></div>
        <div><span>BUYING POWER</span><strong>{money(branch.buyingPowerUsd)}</strong><em>FULL BALANCE BASE</em></div>
        <div><span>POSITIONS</span><strong>{branch.equityPositionCount ?? 0} / {branch.optionPositionCount ?? 0}</strong><em>STOCK / OPTION</em></div>
        <div><span>TWIN EVENTS</span><strong>{branch.paperTwinEventCount ?? 0}</strong><em>HASH-CHAINED</em></div>
      </div>
      <div className="live-branch__controls">
        <div className="live-lane-state"><i className="is-on" /><span>STOCKS</span><strong>{branch.stockExecutionEnabled ? "ON" : "OFF"}</strong></div>
        <button
          aria-pressed={optionsOn}
          className={optionsOn ? "is-on" : "is-off"}
          disabled={busy || branch.optionsExecutionCapable !== true}
          onClick={() => void onOptionsExecution(!optionsOn)}
          type="button"
        >
          <i /><span>OPTIONS</span><strong>{optionsOn ? "ON" : "OFF"}</strong>
        </button>
        <div className="live-lane-state"><i className="is-on" /><span>NO DAY TRADES</span><strong>ENFORCED</strong></div>
        <div className="live-lane-state"><i className="is-on" /><span>PAPER TWIN</span><strong>REQUIRED</strong></div>
      </div>
      <footer><span>{displayLabel(branch.cycleStatus)}</span><time>{formatTimestamp(branch.generatedUtc)}</time></footer>
    </section>
  );
};
