import { InstrumentPanel } from "../components/Instruments";
import { DatasetTable } from "../components/DatasetTable";
import { PageHeader } from "../components/PageHeader";
import { desktopHostCapabilityLabel, displayLabel, executionSealPresentation, formatTimestamp } from "../state";
import type { DopeySnapshot } from "../types";

const constitutionalLaw = [
  "NO BROKER ORDER AUTHORITY",
  "NO ORDER-CONSTRUCTION TOOLS",
  "NO CREDENTIAL ACCESS FROM RESEARCH AGENTS",
  "SIMULATION IS NEVER REALIZED EVIDENCE",
  "NO SIGNAL BYPASSES SETTLEMENT",
  "NO AGENT EXPANDS ITS OWN PERMISSIONS",
] as const;

export const ConstitutionView = ({ snapshot }: { readonly snapshot: DopeySnapshot }) => {
  const seal = executionSealPresentation(snapshot.envelope.executionSeal);
  const hostCapability = desktopHostCapabilityLabel(snapshot.hostCapabilities);
  const sealDetail = seal.state === "sealed"
    ? "Research may observe, reason, challenge, abstain, and learn. It cannot place, construct, route, or authorize a live order."
    : "Execution-seal evidence is not verified. All paper-automation mutation controls remain blocked until the exact constitutional boundary is restored.";
  return (
    <div className="secondary-view constitution-view">
      <PageHeader index="10" thesis="The protected boundary is intentionally boring, explicit, and structurally outside adaptive control." timestamp={snapshot.generatedUtc} timestampText={formatTimestamp(snapshot.generatedUtc)} title="Constitution" />
      <section className={`constitution-seal constitution-seal--${seal.state}`}>
        <div className="constitution-seal__mark" aria-hidden="true"><span>D</span><i /><b /></div>
        <div>
          <span>{seal.state === "sealed" ? "SOVEREIGN RESEARCH AUTHORITY" : "CONSTITUTIONAL EVIDENCE FAILURE"}</span>
          <h2>{seal.label}</h2>
          <p>{sealDetail}</p>
        </div>
        <dl>
          <div><dt>PAPER DOMAIN</dt><dd>{snapshot.envelope.paperOnly === true ? "VERIFIED" : "UNVERIFIED"}</dd></div>
          <div><dt>LIVE BLOCK</dt><dd>{snapshot.envelope.liveBlocked === true ? "VERIFIED" : "UNVERIFIED"}</dd></div>
          <div><dt>SEAL SOURCE</dt><dd>{displayLabel(snapshot.envelope.executionSeal)}</dd></div>
          <div><dt>HOST CAPABILITY</dt><dd title={snapshot.hostCapabilities.detail ?? hostCapability}>{hostCapability}</dd></div>
        </dl>
      </section>
      <div className="constitution-grid">
        <InstrumentPanel className="" code="C-71" meta="NON-EVOLVABLE" title="Permanent laws">
          <ol className="law-list">
            {constitutionalLaw.map((law, index) => <li key={law}><span>{String(index + 1).padStart(2, "0")}</span><strong>{law}</strong></li>)}
          </ol>
        </InstrumentPanel>
        <InstrumentPanel className="" code="C-72" meta={`${snapshot.observatory.constitutionInvariants.length} REPORTED`} title="Runtime invariant register">
          <DatasetTable emptyLabel="INVARIANT TELEMETRY / NOT REPORTED" rows={snapshot.observatory.constitutionInvariants} />
        </InstrumentPanel>
      </div>
    </div>
  );
};
